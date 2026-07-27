# ContextMap Frontend API Contract

Base URL: `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

## Assets

| Method | Path | Query/Body | Response |
|--------|------|------------|----------|
| POST | `/api/v1/upload/file` | `FormData: file` | `{ status, asset_id, current_state, message }` |
| GET | `/api/v1/assets/preview` | `asset_id` | `{ asset_id, raw_path, type }` — prefix with BASE_URL |
| GET | `/api/v1/assets/structure` | `asset_id` | `{ status: success\|processing, data?: { outline: { outline: [...] } } }` |
| GET | `/api/v1/assets/stream` | `asset_id` | SSE: `state_change`, pipeline events, `completed`, `error` |
| POST | `/api/v1/assets/{asset_id}/retry` | — | retry failed asset |

**Removed:** `POST /api/v1/assets/sync` — upload auto-enqueues when `auto_start_on_upload: true`.

### AssetStatus (lowercase)

`uploading` | `raw` | `recognizing` | `embedding` | `structuring` | `kg_extracting` | `ingesting` | `ready` | `failed`

### Modality

`pdf` | `video` | `audio`

## Status

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/status/single_asset` | `{ status, data: Record<asset_id, AssetPayload> \| AssetPayload }` |
| GET | `/api/v1/status/global_assets` | `{ data: { assets_number, active_pipelines, queue_length } }` |
| GET | `/api/v1/status/single_chat` | `?session_id=` → `{ data: SessionDetail }`; no param → `{ data: Record<session_id, SessionSummary> }` |
| GET | `/api/v1/status/global_chats` | `{ data: { chats_number, chats_status, active_turns } }` |

## Chats

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/v1/chats/sessions` | — | `{ session_id, external_id, chat_status }` |
| POST | `/api/v1/chats/sessions/{session_id}/turns` | `{ message }` | `{ turn_seq, session_id }` |
| GET | `/api/v1/chats/stream` | `session_id` | SSE (see below) |

**Flow:** create session → POST turn → open EventSource stream (before or after turn; stream receives events for active turn).

### ChatStatus (lowercase)

`idle` | `preparing` | `researching` | `evaluating` | `strengthening` | `finalizing` | `failed`

### SessionDetail fields

- `session_id`, `chat_name`, `status`, `current_step`
- `messages[]`: `{ id, role, content, seq, created_at }`
- `evidences[]`: `{ id, content, score, metadata, ... }`
- `events[]`: milestone events (no TOKEN in DB)

### Chat SSE event types

SSE `event` name equals payload `type`:

| Event | Payload keys |
|-------|----------------|
| `state_change` | `status` |
| `step_start` | `step`, `status` |
| `evaluation` | `recommendation`, `confidence` |
| `refetch` | `refetch_hint` |
| `evidence_snapshot` | `count` |
| `infer_result` | `kind`, `summary` |
| `token` | `content` (batched) |
| `completed` | — |
| `error` | `message` |
| `ping` | `{}` |

Listen with `addEventListener(eventType, ...)` not only `message`.

## Legacy frontend mistakes (fixed in refactor)

| Old | New |
|-----|-----|
| `chat_id` | `session_id` |
| `message` (chat body field) | `content` |
| `evidence` | `evidences` |
| `POST /chats/create` | `POST /chats/sessions` |
| SSE `?chat_id=&message=` | POST turn + SSE `?session_id=` |
| `?chat_id=` on status | `?session_id=` |
| PascalCase statuses | lowercase enums |
