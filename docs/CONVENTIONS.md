# ContextMap Naming Conventions

This document is the single source of truth for module layout and naming across the repository.

## Layer Responsibilities

| Layer | Directory | Module naming | Role |
|-------|-----------|---------------|------|
| Paths | `paths.py` | single module | `PROJECT_ROOT`, storage dirs, config path |
| Orchestration | `core/` | `*_manager.py`, `*_graph.py` | Cross-stage LangGraph scheduling (`assets_manager`, `chats_manager`, `chats_graph`) |
| Pipeline | `services/{domain}/` | verb / stage names | parse, ingest, retrieval, evaluate, infer (domain capabilities only) |
| Data access | `database/` | `{entity}_repo.py` | ORM models and repositories |
| Tests | `tests/` | `test_{domain}_{feature}.py` | Unit and integration tests |

Top-level chat/asset orchestration **must** live in `core/`, not `services/`. Domain-internal subgraphs (e.g. `services/outline/graph/`) are allowed inside their owning service.

## Standard Service Package Layout

Every active `services/{domain}/` package should follow:

```
services/{domain}/
  __init__.py       # required: __all__ with stable public API
  config.py         # load_{domain}_config(); may re-export related loaders
  types.py          # domain types (see Type Rules below)
  {orchestrator}.py # main entry (evaluate.py, infer.py, search.py, …)
  ...stages...      # single-responsibility stages (fusion.py, rerank.py, route.py)
  prompts/          # optional: *.jinja2 + render_prompt()
  graph/            # optional LangGraph for domain-internal pipelines only
  loaders/|channels/|sandbox/|visual/  # optional subdomains
```

## File Naming Rules

- **Python modules**: `snake_case.py` only
- **Stage modules**: noun stages (`fusion.py`, `dedup.py`, `gates.py`) or `{role}_{noun}.py` (`content_unit_repo.py`)
- **Public entry functions**: `{verb}_{object}` — e.g. `evaluate_evidence`, `run_infer`, `hybrid_search`, `expand_linked_media`
- **LangGraph nodes**: `node_{action}` for both function and graph node id (e.g. `node_prepare`, `node_generate_draft`)
- **Prompt templates**: `snake_case.jinja2` under the owning domain's `prompts/` (chat synthesizer under `core/chats/prompts/`)
- **Tests**: `test_{domain}_{feature}.py`; benchmarks live in `tests/helpers/` without the `test_` prefix
- **Config**: global `configs/contextmap.yaml`; env specs in `environment/`

## Type Rules

- **Pydantic `BaseModel`**: boundary I/O (API payloads, retrieval queries, DB-adjacent schemas) — see `services/retrieval/types.py`
- **`@dataclass`**: internal pipeline reports and intermediate state — see `services/evaluate/types.py`, `services/infer/types.py`
- Do not duplicate the same concept under two type names

## Package Export Policy

Each service package **must** declare `__all__` in `__init__.py` and export only stable public APIs.

| Package | Public exports |
|---------|----------------|
| `retrieval` | `refine_query`, `hybrid_search`, `search_from_context`, `expand_linked_media` |
| `evaluate` | `evaluate_evidence`, `EvaluationReport`, `EvidenceScore`, `InferHints`, `RefetchHint` |
| `infer` | `run_infer`, `InferResult`, `InferTrigger`, `SandboxRequest`, `SandboxResult` |
| `ingest` | `ingest_processed_dir`, `load_ingest_config` |
| `outline` | `generate_outline_for_processed_dir`, `get_outline_graph`, `load_outline_config` |
| `parse` | `run_parse`, `ParseSummary` |
| `kg` | `extract_kg_for_asset_sync`, `load_kg_config` |
| `common` | processed_assets helpers, text_segment, modelscope_download |

Core orchestration public API:

| Module | Public exports |
|--------|----------------|
| `core.chats_graph` | `build_chat_graph`, `should_refetch`, `apply_refetch_hint`, `merge_evidence` |
| `core.chats_manager` | `get_chats_manager`, `ChatsManager` |
| `core.chats.config` | `load_chat_config` |

Import from package roots in application code when possible:

```python
from services.retrieval import hybrid_search, expand_linked_media
from services.evaluate import evaluate_evidence
from core.chats_manager import get_chats_manager
```

## Loader Suffix Convention (intentional difference)

| Suffix | Package | Output |
|--------|---------|--------|
| `{modality}_units.py` | `services/ingest/loaders/` | `IngestUnit` records for DB ingest |
| `{modality}_context.py` | `services/outline/loaders/` | LLM context strings for outline generation |

Do not merge these loader trees; the suffix reflects different downstream consumers.

## Coverage Module Names (avoid collisions)

| Module | Meaning |
|--------|---------|
| `services/parse/asset_coverage.py` | Parse-time asset statistics from middle.json |
| `services/evaluate/coverage.py` | Evidence facet coverage for retrieval evaluation |

## Anti-patterns

- Top-level cross-service LangGraph orchestration in `services/` (use `core/*_graph.py`)
- Chat JSON file persistence (use PostgreSQL `chat_sessions` / `chat_messages` / `chat_evidences` / `chat_turn_events`)
- Duplicate orchestrator files (`run.py` mirroring `evaluate.py` / `infer.py`)
- Empty `__init__.py` on active pipeline packages
- Identical test files with and without domain prefix
- LangGraph node functions without `node_` prefix
- HuggingFace auto-download in evaluate/infer (use ModelScope via `services/common/modelscope_download.py`)

## Module Quick Reference

```
ContextMap/
├── paths.py
├── configs/contextmap.yaml
├── core/
│   ├── assets_manager.py
│   ├── chats_manager.py
│   ├── chats_graph.py
│   └── chats/              prompts/, config.py, llm.py
├── database/               models, schemas, repositories
├── deploy/postgres/        init/ only — fresh cluster bootstrap (no migrations)
├── docs/                   CONVENTIONS.md (this file)
├── environment/
│   ├── requirements.txt    main pip deps
│   └── infer-sandbox.yaml    isolated conda env for infer sandbox
├── services/
│   ├── common/
│   ├── parse/
│   ├── ingest/
│   ├── outline/
│   ├── kg/
│   ├── retrieval/
│   ├── evaluate/
│   └── infer/
└── tests/                  test_{domain}_{feature}.py, helpers/
```
