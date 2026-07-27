#!/usr/bin/env bash
# Pre-download model weights (wrapper for ContextMap CLI).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${CONTEXTMAP_MODEL_PROFILE:-core}"
YES_FLAG=()
if [[ "${CONTEXTMAP_MODELS_YES:-}" == "1" ]]; then
  YES_FLAG=(-y)
fi

exec python3 "$ROOT/contextmap.py" models download --profile "$PROFILE" "${YES_FLAG[@]}" "$@"
