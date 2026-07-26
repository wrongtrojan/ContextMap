"""Load chat orchestration settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG


def _defaults() -> dict[str, Any]:
    return {
        "research": {
            "max_retries": 2,
            "merge_evidence_on_refetch": True,
            "stop_loss_confidence": 0.6,
        },
        "expand_media": {
            "window_sec": 2.0,
        },
        "llm": {"inherit": "outline"},
        "context_window_messages": 6,
    }


def load_chat_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = _defaults()
    raw = dict(data.get("chat") or {})
    merged: dict[str, Any] = {**defaults, **raw}
    for key in ("research", "expand_media", "llm"):
        if key in raw and isinstance(raw[key], dict):
            merged[key] = {**defaults.get(key, {}), **raw[key]}
    return merged
