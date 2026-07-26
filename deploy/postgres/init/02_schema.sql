-- ContextMap PostgreSQL schema (fresh install via docker-entrypoint-initdb.d).

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE asset_modality AS ENUM ('pdf', 'video', 'audio');

CREATE TYPE asset_status AS ENUM (
    'uploading',
    'raw',
    'recognizing',
    'embedding',
    'structuring',
    'kg_extracting',
    'ingesting',
    'ready',
    'failed'
);

CREATE TYPE kg_status AS ENUM (
    'pending',
    'extracting',
    'ready',
    'partial',
    'failed',
    'skipped'
);

CREATE TYPE content_type AS ENUM (
    'text',
    'image',
    'table',
    'transcript',
    'frame',
    'transcript_context'
);

CREATE TYPE chat_status AS ENUM (
    'idle',
    'preparing',
    'researching',
    'evaluating',
    'strengthening',
    'finalizing',
    'failed'
);

CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system');

CREATE TYPE pipeline_event_type AS ENUM (
    'status_change',
    'step_start',
    'step_complete',
    'step_failed',
    'retry'
);

CREATE TYPE chat_turn_event_type AS ENUM (
    'status_change',
    'step_start',
    'step_complete',
    'step_failed',
    'evaluation',
    'refetch',
    'evidence_snapshot',
    'infer_result',
    'token',
    'completed',
    'error'
);

-- ---------------------------------------------------------------------------
-- Functions
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Assets & retrieval
-- ---------------------------------------------------------------------------

CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(500) NOT NULL,
    modality asset_modality NOT NULL,
    status asset_status NOT NULL DEFAULT 'uploading',
    kg_status kg_status NOT NULL DEFAULT 'pending',
    raw_path VARCHAR(1000) NOT NULL,
    processed_path VARCHAR(1000),
    file_size_bytes BIGINT,
    file_hash VARCHAR(64),
    retry_count INTEGER NOT NULL DEFAULT 0,
    triple_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_assets_status ON assets (status);
CREATE INDEX idx_assets_modality ON assets (modality);
CREATE INDEX idx_assets_kg_status ON assets (kg_status);
CREATE INDEX idx_assets_created_at ON assets (created_at DESC);
CREATE UNIQUE INDEX idx_assets_file_hash ON assets (file_hash) WHERE file_hash IS NOT NULL;

CREATE TRIGGER trg_assets_updated_at
    BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE content_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    content_type content_type NOT NULL,
    search_text TEXT NOT NULL,
    search_tokens TEXT,
    content_ref TEXT NOT NULL,
    embedding vector(1024),
    timestamp_anchor DOUBLE PRECISION NOT NULL DEFAULT 0,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_content_units_asset_id ON content_units (asset_id);
CREATE INDEX idx_content_units_type ON content_units (content_type);
CREATE INDEX idx_content_units_anchor ON content_units (asset_id, timestamp_anchor);
CREATE UNIQUE INDEX idx_content_units_asset_chunk ON content_units (asset_id, chunk_index, content_type);
CREATE INDEX idx_content_units_embedding_hnsw
    ON content_units USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_content_units_search_tokens_gin
    ON content_units USING GIN (to_tsvector('simple', COALESCE(search_tokens, search_text)));

CREATE TABLE outlines (
    asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    title VARCHAR(500),
    tree JSONB NOT NULL DEFAULT '[]',
    model_id VARCHAR(100),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outlines_tree_gin ON outlines USING GIN (tree);

CREATE TRIGGER trg_outlines_updated_at
    BEFORE UPDATE ON outlines
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Chat
-- ---------------------------------------------------------------------------

CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(32) NOT NULL UNIQUE,
    chat_name VARCHAR(200) NOT NULL,
    status chat_status NOT NULL DEFAULT 'idle',
    retry_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_sessions_status ON chat_sessions (status);
CREATE INDEX idx_chat_sessions_updated ON chat_sessions (updated_at DESC);

CREATE TRIGGER trg_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    content TEXT NOT NULL,
    seq INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_chat_messages_session_seq ON chat_messages (session_id, seq);
CREATE INDEX idx_chat_messages_session_created ON chat_messages (session_id, created_at);

CREATE TABLE chat_evidences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    content_unit_id UUID REFERENCES content_units(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    base_vector_score DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}',
    rank INTEGER NOT NULL DEFAULT 0,
    source VARCHAR(32) NOT NULL DEFAULT 'pgvector',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_evidences_session ON chat_evidences (session_id);
CREATE INDEX idx_chat_evidences_message ON chat_evidences (message_id);
CREATE INDEX idx_chat_evidences_score ON chat_evidences (session_id, score DESC);

CREATE TABLE chat_turn_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    turn_seq INTEGER NOT NULL,
    event_type chat_turn_event_type NOT NULL,
    step_name VARCHAR(64),
    from_status chat_status,
    to_status chat_status,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_turn_events_session
    ON chat_turn_events (session_id, turn_seq, created_at);

-- ---------------------------------------------------------------------------
-- Pipeline & KG
-- ---------------------------------------------------------------------------

CREATE TABLE pipeline_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    event_type pipeline_event_type NOT NULL,
    from_status asset_status,
    to_status asset_status,
    step_name VARCHAR(64),
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_events_asset ON pipeline_events (asset_id, created_at DESC);

CREATE TABLE kg_jobs (
    asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    status kg_status NOT NULL DEFAULT 'pending',
    chunks_total INTEGER NOT NULL DEFAULT 0,
    chunks_processed INTEGER NOT NULL DEFAULT 0,
    triples_extracted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_kg_jobs_updated_at
    BEFORE UPDATE ON kg_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
