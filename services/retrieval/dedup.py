"""Deduplication and ranking for retrieval results."""

from __future__ import annotations

import math
import re
import uuid

from services.retrieval.types import ScoredHit


def normalize_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned


def dedup_exact_id(hits: list[ScoredHit]) -> tuple[list[ScoredHit], int]:
    seen: set[uuid.UUID] = set()
    kept: list[ScoredHit] = []
    removed = 0
    for hit in hits:
        if hit.unit_id in seen:
            removed += 1
            continue
        seen.add(hit.unit_id)
        kept.append(hit)
    return kept, removed


def dedup_text(hits: list[ScoredHit], *, enabled: bool) -> tuple[list[ScoredHit], int]:
    if not enabled:
        return hits, 0
    seen: set[str] = set()
    kept: list[ScoredHit] = []
    removed = 0
    for hit in hits:
        key = normalize_text(hit.unit.search_text or hit.unit.content_ref)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(hit)
    return kept, removed


def _structural_key(hit: ScoredHit, time_window_sec: float) -> tuple:
    """PDF: per chunk (page + chunk_index). AV: time bucket to collapse transcript overlap."""
    unit = hit.unit
    modality = hit.asset.modality.value
    if modality == "pdf":
        page = int(unit.timestamp_anchor)
        meta_page = (unit.metadata or {}).get("page_label")
        if meta_page is not None:
            page = int(meta_page)
        return (hit.asset.id, "pdf", page, unit.chunk_index)
    bucket = int(unit.timestamp_anchor // max(time_window_sec, 1.0))
    return (hit.asset.id, modality, bucket)


def dedup_structural(
    hits: list[ScoredHit],
    *,
    time_window_sec: float,
) -> tuple[list[ScoredHit], int]:
    seen: set[tuple] = set()
    kept: list[ScoredHit] = []
    removed = 0
    for hit in hits:
        key = _structural_key(hit, time_window_sec)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(hit)
    return kept, removed


def protect_keyword_hits(
    hits: list[ScoredHit],
    *,
    protect_top_n: int,
    min_keyword_score: float,
) -> tuple[list[ScoredHit], int]:
    """Reserve slots for high-confidence keyword hits before final truncation."""
    if protect_top_n <= 0 or not hits:
        return hits, 0

    keyword_candidates = sorted(
        [hit for hit in hits if (hit.keyword_score or 0.0) >= min_keyword_score],
        key=lambda hit: (-(hit.keyword_score or 0.0), -hit.final_score),
    )
    protected: list[ScoredHit] = []
    seen: set[uuid.UUID] = set()
    for hit in keyword_candidates:
        if len(protected) >= protect_top_n:
            break
        if hit.unit_id in seen:
            continue
        protected.append(hit)
        seen.add(hit.unit_id)

    if not protected:
        return hits, 0

    rest = [hit for hit in hits if hit.unit_id not in seen]
    return protected + rest, len(protected)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def mmr_select(
    hits: list[ScoredHit],
    *,
    top_k: int,
    pool_multiplier: float,
    mmr_lambda: float,
) -> tuple[list[ScoredHit], int]:
    if not hits:
        return [], 0
    pool_size = min(len(hits), max(top_k, int(top_k * pool_multiplier)))
    pool = hits[:pool_size]
    selected: list[ScoredHit] = []
    remaining = list(pool)

    while remaining and len(selected) < top_k:
        best_idx = 0
        best_score = float("-inf")
        for idx, candidate in enumerate(remaining):
            relevance = candidate.final_score
            redundancy = 0.0
            if selected and candidate.unit.embedding:
                similarities = [
                    _cosine(candidate.unit.embedding or [], prev.unit.embedding or [])
                    for prev in selected
                    if prev.unit.embedding
                ]
                if similarities:
                    redundancy = max(similarities)
            mmr_score = mmr_lambda * relevance - (1.0 - mmr_lambda) * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        selected.append(remaining.pop(best_idx))

    removed = max(0, len(hits) - len(selected))
    return selected, removed


def deduplicate_and_rank(
    hits: list[ScoredHit],
    *,
    top_k: int,
    config: dict,
) -> tuple[list[ScoredHit], dict[str, int]]:
    """Recall-first order: exact → text → structural → keyword protect → top_k."""
    dedup_cfg = config.get("dedup") or {}
    stats: dict[str, int] = {}

    hits, n = dedup_exact_id(hits)
    stats["exact_id"] = n

    hits, n = dedup_text(hits, enabled=bool(dedup_cfg.get("text_normalize", True)))
    stats["text"] = n

    hits, n = dedup_structural(
        hits,
        time_window_sec=float(dedup_cfg.get("time_window_sec", 30)),
    )
    stats["structural"] = n

    hits, n = protect_keyword_hits(
        hits,
        protect_top_n=int(dedup_cfg.get("protect_keyword_top_n", 3)),
        min_keyword_score=float(dedup_cfg.get("protect_keyword_min_score", 0.5)),
    )
    stats["keyword_protected"] = n

    if bool(dedup_cfg.get("mmr_enabled", False)):
        hits, n = mmr_select(
            hits,
            top_k=top_k,
            pool_multiplier=float(dedup_cfg.get("mmr_pool_multiplier", 5)),
            mmr_lambda=float(dedup_cfg.get("mmr_lambda", 0.7)),
        )
        stats["mmr_pool"] = n
    elif len(hits) > top_k:
        stats["mmr_pool"] = len(hits) - top_k
        hits = hits[:top_k]
    else:
        stats["mmr_pool"] = 0

    return hits, stats
