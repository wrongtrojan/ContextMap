"""Load KG settings from configs/contextmap.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG


def load_kg_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults: dict[str, Any] = {
        "enabled": True,
        "chunk_max_tokens": 512,
        "fail_open": True,
        "autore": {
            "base_modelscope_repo": "AI-ModelScope/Mistral-7B-v0.1",
            "adapter_repo": "dante123/AutoRE",
            "model_dir": "models/autore",
            "hf_endpoint": "https://hf-mirror.com",
            "auto_download": True,
            "device": "cuda",
            "load_in_4bit": True,
            "max_new_tokens": 512,
            "open_domain": True,
        },
        "age": {
            "graph_name": "contextmap",
            "entity_merge_normalize": True,
        },
        "extract": {
            "content_types": ["text", "transcript"],
        },
    }
    kg = dict(data.get("kg") or {})
    merged = {**defaults, **kg}
    merged["autore"] = {**defaults["autore"], **(kg.get("autore") or {})}
    merged["age"] = {**defaults["age"], **(kg.get("age") or {})}
    merged["extract"] = {**defaults["extract"], **(kg.get("extract") or {})}
    return merged


def load_pipeline_kg_concurrency(path: Path | None = None) -> int:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    pipeline = data.get("pipeline") or {}
    return int(pipeline.get("max_concurrent_kg", 1))
