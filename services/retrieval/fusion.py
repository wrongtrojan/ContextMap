"""RRF fusion with channel quality gates and multi-channel consensus."""

from __future__ import annotations

import uuid
from typing import Any

from database.enums import AssetModality, ContentType
from services.retrieval.types import ChannelHit, RetrievalQuery, ScoredHit


def _channel_eligible(channel: str, hit: ChannelHit, fusion_cfg: dict[str, Any]) -> bool:
    """Drop weak single-channel hits before they enter RRF (score-scale aware)."""
    if channel == "vector":
        return hit.score >= float(fusion_cfg.get("min_vector_score", 0.55))
    if channel == "keyword":
        return hit.score >= float(fusion_cfg.get("min_keyword_score", 0.15))
    if channel == "graph":
        return hit.score >= float(fusion_cfg.get("min_graph_score", 0.20))
    return True


def reciprocal_rank_fusion(
    channel_hits: dict[str, list[ChannelHit]],
    *,
    weights: dict[str, float],
    rrf_k: int,
    fusion_cfg: dict[str, Any] | None = None,
) -> dict[uuid.UUID, float]:
    fusion_cfg = fusion_cfg or {}
    score_blend = float(fusion_cfg.get("score_blend", 0.4))
    intersection_mult = float(fusion_cfg.get("intersection_multiplier", 1.5))
    intersection_min_keyword = float(fusion_cfg.get("intersection_min_keyword", 0.5))
    intersection_min_vector = float(fusion_cfg.get("intersection_min_vector", 0.65))
    single_vector_discount = float(fusion_cfg.get("single_vector_discount", 0.7))
    high_vector_score = float(fusion_cfg.get("high_vector_score", 0.78))

    per_unit_channels: dict[uuid.UUID, set[str]] = {}
    per_unit_vector_score: dict[uuid.UUID, float] = {}
    per_unit_keyword_score: dict[uuid.UUID, float] = {}
    scores: dict[uuid.UUID, float] = {}

    for channel, hits in channel_hits.items():
        weight = float(weights.get(channel, 0.0))
        if weight <= 0:
            continue
        for hit in hits:
            if not _channel_eligible(channel, hit, fusion_cfg):
                continue
            score_factor = 1.0 + score_blend * max(hit.score, 0.0)
            contrib = weight * score_factor / (rrf_k + hit.rank)
            scores[hit.unit_id] = scores.get(hit.unit_id, 0.0) + contrib
            per_unit_channels.setdefault(hit.unit_id, set()).add(channel)
            if channel == "vector":
                per_unit_vector_score[hit.unit_id] = hit.score
            if channel == "keyword":
                per_unit_keyword_score[hit.unit_id] = hit.score

    for unit_id, base in list(scores.items()):
        channels = per_unit_channels.get(unit_id, set())
        if len(channels) >= 2:
            kw = per_unit_keyword_score.get(unit_id, 0.0)
            vec = per_unit_vector_score.get(unit_id, 0.0)
            if kw >= intersection_min_keyword and vec >= intersection_min_vector:
                scores[unit_id] = base * intersection_mult
        elif channels == {"vector"}:
            vec_score = per_unit_vector_score.get(unit_id, 0.0)
            if vec_score < high_vector_score:
                scores[unit_id] = base * single_vector_discount
    return scores


def apply_preference_boosts(
    hit: ScoredHit,
    query: RetrievalQuery,
    *,
    boost_cfg: dict[str, float],
) -> dict[str, float]:
    boosts: dict[str, float] = {}
    prefs = query.preferences
    asset = hit.asset
    unit = hit.unit
    content = _content_for_boost(hit)

    if prefs.asset_name and prefs.asset_name.lower() in asset.name.lower():
        boosts["asset_name"] = float(boost_cfg.get("asset_name_boost", 0.12))

    if prefs.modality and prefs.modality.lower() == asset.modality.value:
        boosts["modality"] = float(boost_cfg.get("modality_boost", 0.08))

    if prefs.timestamp is not None:
        try:
            if abs(float(unit.timestamp_anchor) - float(prefs.timestamp)) < 0.01:
                boosts["timestamp"] = float(boost_cfg.get("timestamp_boost", 0.15))
        except (TypeError, ValueError):
            pass

    query_lower = (query.semantic_query or query.query_text).lower()
    if query_lower and query_lower in content.lower():
        boosts["content_substring"] = float(boost_cfg.get("content_substring_boost", 0.06))

    if asset.modality == AssetModality.PDF and unit.content_type == ContentType.TEXT:
        block_type = (unit.metadata or {}).get("block_type")
        if block_type in ("title", "heading"):
            boosts["pdf_title"] = float(boost_cfg.get("pdf_title_boost", 0.05))

    if asset.modality in (AssetModality.VIDEO, AssetModality.AUDIO) and unit.content_type == ContentType.TRANSCRIPT:
        boosts["video_transcript"] = float(boost_cfg.get("video_transcript_boost", 0.03))

    return boosts


def _content_for_boost(hit: ScoredHit) -> str:
    unit = hit.unit
    if unit.content_type in (ContentType.IMAGE, ContentType.FRAME, ContentType.TABLE):
        return unit.search_text or unit.content_ref
    return unit.content_ref or unit.search_text


def fuse_channel_hits(
    channel_hits: dict[str, list[ChannelHit]],
    query: RetrievalQuery,
    *,
    config: dict[str, Any],
) -> list[ScoredHit]:
    fusion_cfg = config.get("fusion") or {}
    boost_cfg = config.get("preferences") or {}
    weights = {
        ch: float((config.get("channels") or {}).get(ch, {}).get("weight", 1.0))
        for ch in ("vector", "keyword", "graph")
    }
    rrf_k = int(fusion_cfg.get("rrf_k", 60))
    rrf_scores = reciprocal_rank_fusion(
        channel_hits,
        weights=weights,
        rrf_k=rrf_k,
        fusion_cfg=fusion_cfg,
    )

    by_id: dict[uuid.UUID, ChannelHit] = {}
    channel_scores: dict[uuid.UUID, dict[str, float]] = {}
    sources: dict[uuid.UUID, set[str]] = {}

    for channel, hits in channel_hits.items():
        for hit in hits:
            if not _channel_eligible(channel, hit, fusion_cfg):
                continue
            by_id[hit.unit_id] = hit
            channel_scores.setdefault(hit.unit_id, {})[channel] = hit.score
            sources.setdefault(hit.unit_id, set()).add(channel)

    scored: list[ScoredHit] = []
    for unit_id, rrf_score in rrf_scores.items():
        base = by_id.get(unit_id)
        if base is None or base.unit is None or base.asset is None:
            continue
        ch_scores = channel_scores.get(unit_id, {})
        item = ScoredHit(
            unit_id=unit_id,
            unit=base.unit,
            asset=base.asset,
            rrf_score=rrf_score,
            final_score=rrf_score,
            vector_score=ch_scores.get("vector"),
            keyword_score=ch_scores.get("keyword"),
            graph_score=ch_scores.get("graph"),
            sources=sorted(sources.get(unit_id, set())),
        )
        boosts = apply_preference_boosts(item, query, boost_cfg=boost_cfg)
        item.boosts = boosts
        boost_factor = 1.0 + sum(boosts.values())
        item.final_score = rrf_score * boost_factor
        scored.append(item)

    scored.sort(key=lambda item: item.final_score, reverse=True)
    return scored
