"""Load evaluate settings from configs/contextmap.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG


def _defaults() -> dict[str, Any]:
    return {
        "reranker": {
            "model_dir": "models/bge-reranker-v2-m3",
            "modelscope_repo": "BAAI/bge-reranker-v2-m3",
            "batch_size": 16,
            "device": "cpu",
        },
        "thresholds": {
            "proceed_rerank": 0.55,
            "min_coverage": 0.60,
            "min_keep_score": 0.35,
            "audit_on_borderline": True,
            "borderline_low": 0.40,
            "borderline_high": 0.55,
        },
        "keep_top_k": 8,
        "llm": {"inherit": "outline"},
    }


def load_evaluate_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = _defaults()
    raw = dict(data.get("evaluate") or {})
    merged: dict[str, Any] = {**defaults, **raw}
    for key in ("reranker", "thresholds", "llm"):
        if key in raw and isinstance(raw[key], dict):
            merged[key] = {**defaults.get(key, {}), **raw[key]}
    return merged


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    evaluate = load_evaluate_config(config_path)
    llm_cfg = dict(evaluate.get("llm") or {})
    if llm_cfg.get("inherit") == "outline":
        outline = dict(data.get("outline") or {})
        outline_llm = dict(outline.get("llm") or {})
        return {"llm": {**outline_llm, **{k: v for k, v in llm_cfg.items() if k != "inherit"}}}
    return {"llm": llm_cfg}
