"""BGE cross-encoder reranking."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Callable

from paths import PROJECT_ROOT
from services.common.modelscope_download import ensure_model_dir
from services.evaluate.config import load_evaluate_config

ScoreFn = Callable[[str, list[str]], list[float]]


def _sigmoid(value: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-value))


@lru_cache(maxsize=1)
def _get_cross_encoder():
    cfg = load_evaluate_config()
    reranker_cfg = cfg.get("reranker") or {}
    model_dir = PROJECT_ROOT / str(reranker_cfg.get("model_dir", "models/bge-reranker-v2-m3"))
    modelscope_repo = str(reranker_cfg.get("modelscope_repo", "BAAI/bge-reranker-v2-m3"))
    device = str(reranker_cfg.get("device", "cpu"))

    ensure_model_dir(model_dir=model_dir, modelscope_repo=modelscope_repo)

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for reranking. "
            "Install with: pip install sentence-transformers"
        ) from exc

    return CrossEncoder(str(model_dir), device=device), cfg


def rerank_scores(query: str, passages: list[str], *, score_fn: ScoreFn | None = None) -> list[float]:
    if not passages:
        return []
    if score_fn is not None:
        return score_fn(query, passages)

    model, cfg = _get_cross_encoder()
    batch_size = int((cfg.get("reranker") or {}).get("batch_size", 16))
    pairs = [(query, passage) for passage in passages]
    raw_scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
    normalized: list[float] = []
    for raw in raw_scores:
        value = float(raw)
        if value < 0.0 or value > 1.0:
            value = _sigmoid(value)
        normalized.append(max(0.0, min(1.0, value)))
    return normalized


async def rerank_evidence(
    *,
    query: str,
    evidence: list[dict],
    score_fn: ScoreFn | None = None,
) -> list[tuple[dict, float]]:
    passages = [str(item.get("content") or "") for item in evidence]
    scores = await asyncio.to_thread(rerank_scores, query, passages, score_fn=score_fn)
    ranked = list(zip(evidence, scores))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return ranked
