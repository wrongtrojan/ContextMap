"""Model download profiles derived from configs/contextmap.yaml."""

from __future__ import annotations

from dataclasses import dataclass

from paths import CONTEXTMAP_CONFIG


@dataclass(frozen=True)
class ModelSpec:
    key: str
    section: str
    label: str
    size_hint: str
    kind: str = "modelscope"  # modelscope | autore


MODEL_SPECS: dict[str, ModelSpec] = {
    "embedding": ModelSpec(
        key="embedding",
        section="embedding",
        label="BGE-M3 embedding",
        size_hint="~2 GB",
    ),
    "whisper": ModelSpec(
        key="whisper",
        section="whisper",
        label="faster-whisper large-v3",
        size_hint="~3 GB",
    ),
    "reranker": ModelSpec(
        key="reranker",
        section="evaluate.reranker",
        label="BGE reranker v2-m3",
        size_hint="~2 GB",
    ),
    "visual": ModelSpec(
        key="visual",
        section="infer.visual",
        label="Qwen2-VL-7B-Instruct",
        size_hint="~16 GB",
    ),
    "autore": ModelSpec(
        key="autore",
        section="kg.autore",
        label="AutoRE (Mistral-7B base + LoRA adapters)",
        size_hint="~15 GB",
        kind="autore",
    ),
}

PROFILES: dict[str, list[str]] = {
    "minimal": ["embedding", "whisper"],
    "core": ["embedding", "whisper", "reranker"],
    "full": ["embedding", "whisper", "reranker", "visual"],
    "kg": ["autore"],
    "all": ["embedding", "whisper", "reranker", "visual", "autore"],
}

DEFAULT_PROFILE = "core"
DEFAULT_CONFIG = CONTEXTMAP_CONFIG
