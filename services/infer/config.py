"""Load infer settings from configs/contextmap.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG


def _defaults() -> dict[str, Any]:
    return {
        "sandbox": {
            "enabled": True,
            "conda_python": None,
            "timeout_sec": 30,
        },
        "visual": {
            "enabled": True,
            "model_dir": "models/qwen2-vl-7b-instruct",
            "modelscope_repo": "qwen/Qwen2-VL-7B-Instruct",
            "timeout_sec": 120,
            "max_images": 4,
            "device": "cuda",
        },
        "route": {
            "sandbox_keywords": ["计算", "求解", "验证", "equation", "prove"],
            "visual_content_types": ["frame", "image", "table"],
            "visual_min_rerank": 0.45,
        },
        "llm": {"inherit": "outline"},
    }


def load_infer_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = _defaults()
    raw = dict(data.get("infer") or {})
    merged: dict[str, Any] = {**defaults, **raw}
    for key in ("sandbox", "visual", "route", "llm"):
        if key in raw and isinstance(raw[key], dict):
            merged[key] = {**defaults.get(key, {}), **raw[key]}
    return merged


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    infer = load_infer_config(config_path)
    llm_cfg = dict(infer.get("llm") or {})
    if llm_cfg.get("inherit") == "outline":
        outline = dict(data.get("outline") or {})
        outline_llm = dict(outline.get("llm") or {})
        return {"llm": {**outline_llm, **{k: v for k, v in llm_cfg.items() if k != "inherit"}}}
    return {"llm": llm_cfg}
