# ContextMap environment setup

Single entry point for Python dependencies, conda environments, and secrets.

## Main environment

```bash
conda create -n ContextMap python=3.11
conda activate ContextMap
pip install -r environment/requirements-dev.txt
```

`requirements-dev.txt` includes runtime deps (`requirements.txt`) plus pytest/httpx for tests.

Visual inference deps (vLLM, flash-attn) are included in `requirements.txt`. On CPU-only hosts, set `infer.visual.enabled: false` in `configs/contextmap.yaml` (default for live E2E). If `flash-attn` fails to install, skip it temporarily and disable visual infer.

## Infer sandbox (isolated conda)

For the scientific sandbox used by `services/infer`:

```bash
conda env create -f environment/infer-sandbox.yaml
```

The env name must match `infer.sandbox.conda_env` in `configs/contextmap.yaml` (default: `infer-sandbox`).

## Secrets and overrides

Configure `DEEPSEEK_API_KEY` via **Workbench → Settings** (saved to `storage/local/secrets.env`), or set process environment variables for Docker/CI.

| Variable | Used by | Default (if unset) |
|----------|---------|-------------------|
| `DEEPSEEK_API_KEY` | outline LLM, chat, live E2E | required for LLM features |
| `POSTGRES_PASSWORD` | `database/config.py` | `contextmap` (see `configs/contextmap.yaml`) |
| `MINIO_SECRET_KEY` | `services/ingest/minio_client.py` | `contextmap123` |
| `HF_ENDPOINT` | `services/kg/autore_runtime.py` | HuggingFace default |
| `LIVE_ENABLE_INFER` | live E2E tests | unset = infer disabled in live tests |

Docker Compose (`deploy/docker-compose.yml`) uses the same Postgres/MinIO credentials as `configs/contextmap.yaml`.

## Bootstrap checklist

1. `sudo bash deploy/installer.sh && sudo docker compose -f deploy/docker-compose.yml up -d`
2. `bash models/downloader.sh`
3. `python configs/calibrator.py`
4. Open Workbench Settings (or set `DEEPSEEK_API_KEY` in env / `storage/local/secrets.env`)
5. Ingest sample corpus (see project README / docs)
