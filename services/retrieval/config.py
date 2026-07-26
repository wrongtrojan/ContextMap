"""Load retrieval settings from configs/contextmap.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG


def _defaults() -> dict[str, Any]:
    """Defaults aligned with configs/contextmap.yaml (used when keys are absent)."""
    return {
        "top_k_default": 8,
        "candidate_multiplier": 5,
        "llm": {"inherit": "outline"},
        "prompts": {"version": "2026-07-26"},
        "channels": {
            "vector": {"enabled": True, "weight": 0.85},
            "keyword": {"enabled": True, "weight": 1.0},
            "graph": {
                "enabled": False,
                "weight": 0.6,
                "fail_open": True,
                "depth": 2,
                "entity_limit": 50,
            },
        },
        "fusion": {
            "method": "rrf",
            "rrf_k": 60,
            "score_blend": 0.4,
            "min_vector_score": 0.55,
            "min_keyword_score": 0.15,
            "min_graph_score": 0.20,
            "intersection_multiplier": 1.5,
            "intersection_min_keyword": 0.5,
            "intersection_min_vector": 0.65,
            "single_vector_discount": 0.7,
            "high_vector_score": 0.78,
        },
        "dedup": {
            "text_normalize": True,
            "time_window_sec": 30,
            "mmr_enabled": False,
            "protect_keyword_top_n": 3,
            "protect_keyword_min_score": 0.5,
            "mmr_lambda": 0.7,
            "mmr_pool_multiplier": 5,
        },
        "preferences": {
            "asset_name_boost": 0.12,
            "modality_boost": 0.08,
            "timestamp_boost": 0.15,
            "content_substring_boost": 0.06,
            "pdf_title_boost": 0.05,
            "video_transcript_boost": 0.03,
        },
        "filters": {"asset_status": "ready"},
        "keyword": {"segment_chinese": True, "fts_config": "simple"},
    }


def load_retrieval_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = _defaults()
    raw = dict(data.get("retrieval") or {})
    merged: dict[str, Any] = {**defaults, **raw}
    for key in ("channels", "fusion", "dedup", "preferences", "filters", "prompts", "llm", "keyword"):
        if key in raw and isinstance(raw[key], dict):
            merged[key] = {**defaults.get(key, {}), **raw[key]}
    for channel in ("vector", "keyword", "graph"):
        merged["channels"][channel] = {
            **defaults["channels"][channel],
            **(raw.get("channels") or {}).get(channel, {}),
        }

    kg_enabled = bool((data.get("kg") or {}).get("enabled", False))
    if not kg_enabled:
        merged["channels"]["graph"]["enabled"] = False

    return merged


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    """Resolve LLM config for query refinement (inherit outline by default)."""
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    retrieval = load_retrieval_config(config_path)
    llm_cfg = dict(retrieval.get("llm") or {})
    if llm_cfg.get("inherit") == "outline":
        outline = dict(data.get("outline") or {})
        outline_llm = dict(outline.get("llm") or {})
        return {"llm": {**outline_llm, **{k: v for k, v in llm_cfg.items() if k != "inherit"}}}
    return {"llm": llm_cfg}
