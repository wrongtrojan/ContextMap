#!/usr/bin/env bash
# Prepare storage dirs and start Postgres/MinIO via Docker Compose.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/contextmap.py" setup --skip-models --skip-secrets --skip-calibrate "$@"
