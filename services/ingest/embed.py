"""BGE-M3 text embedding."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROJECT_ROOT
from services.common.modelscope_download import ensure_model_dir, is_model_ready

CONFIG_PATH = CONTEXTMAP_CONFIG


def load_embedding_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return dict(data.get("embedding") or {})


def _model_dir(cfg: dict[str, Any]) -> Path:
    return PROJECT_ROOT / cfg.get("model_dir", "models/bge-m3")


@lru_cache(maxsize=1)
def _get_model():
    cfg = load_embedding_config()
    model_dir = _model_dir(cfg)
    device = cfg.get("device", "cpu")

    if not is_model_ready(model_dir):
        ensure_model_dir(
            model_dir=model_dir,
            modelscope_repo=str(cfg.get("modelscope_repo", "BAAI/bge-m3")),
        )

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for embedding. "
            "Install with: pip install sentence-transformers"
        ) from exc

    model = SentenceTransformer(str(model_dir), device=device)
    return model, cfg


def embedding_dim() -> int:
    return int(load_embedding_config().get("dim", 1024))


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model, cfg = _get_model()
    batch_size = int(cfg.get("batch_size", 16))
    normalize = bool(cfg.get("normalize", True))
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=normalize,
        show_progress_bar=len(texts) > 32,
    )
    return [vector.tolist() for vector in vectors]
