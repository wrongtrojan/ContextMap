"""Unit tests for RRF fusion."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from database.enums import AssetModality, AssetStatus, ContentType, KgStatus
from database.schemas import AssetRead, ContentUnitRead
from services.retrieval.fusion import fuse_channel_hits, reciprocal_rank_fusion
from services.retrieval.types import ChannelHit, RetrievalQuery, SearchPreferences


def _unit(unit_id: uuid.UUID, asset_id: uuid.UUID) -> ContentUnitRead:
    return ContentUnitRead(
        id=unit_id,
        asset_id=asset_id,
        content_type=ContentType.TEXT,
        search_text="sample text",
        content_ref="sample text",
        embedding=None,
        timestamp_anchor=1.0,
        chunk_index=0,
        metadata_={},
        created_at=datetime.now(timezone.utc),
    )


def _asset(asset_id: uuid.UUID) -> AssetRead:
    now = datetime.now(timezone.utc)
    return AssetRead(
        id=asset_id,
        name="test-asset",
        modality=AssetModality.PDF,
        status=AssetStatus.READY,
        kg_status=KgStatus.SKIPPED,
        raw_path="raw",
        processed_path="processed",
        file_size_bytes=100,
        file_hash="abc",
        retry_count=0,
        triple_count=0,
        error_message=None,
        metadata_={},
        created_at=now,
        updated_at=now,
    )


def test_rrf_single_channel():
    uid = uuid.uuid4()
    hits = [ChannelHit(unit_id=uid, score=0.9, channel="vector", rank=1)]
    scores = reciprocal_rank_fusion(
        {"vector": hits},
        weights={"vector": 1.0},
        rrf_k=60,
        fusion_cfg={"score_blend": 0.4},
    )
    assert uid in scores
    assert scores[uid] == pytest.approx((1.0 + 0.4 * 0.9) / 61)


def test_rrf_multi_channel():
    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    channel_hits = {
        "vector": [
            ChannelHit(unit_id=uid_a, score=0.9, channel="vector", rank=1),
            ChannelHit(unit_id=uid_b, score=0.8, channel="vector", rank=2),
        ],
        "keyword": [
            ChannelHit(unit_id=uid_b, score=0.7, channel="keyword", rank=1),
        ],
    }
    scores = reciprocal_rank_fusion(
        channel_hits,
        weights={"vector": 0.85, "keyword": 1.0},
        rrf_k=60,
        fusion_cfg={"intersection_multiplier": 1.5},
    )
    assert scores[uid_b] > scores[uid_a]


def test_rrf_vector_gate_excludes_noise():
    uid = uuid.uuid4()
    hits = [ChannelHit(unit_id=uid, score=0.30, channel="vector", rank=1)]
    scores = reciprocal_rank_fusion(
        {"vector": hits},
        weights={"vector": 1.0},
        rrf_k=60,
        fusion_cfg={"min_vector_score": 0.55},
    )
    assert uid not in scores


def test_rrf_intersection_multiplier():
    uid = uuid.uuid4()
    channel_hits = {
        "vector": [ChannelHit(unit_id=uid, score=0.90, channel="vector", rank=1)],
        "keyword": [ChannelHit(unit_id=uid, score=0.80, channel="keyword", rank=1)],
    }
    dual = reciprocal_rank_fusion(
        channel_hits,
        weights={"vector": 0.85, "keyword": 1.0},
        rrf_k=60,
        fusion_cfg={
            "intersection_multiplier": 1.5,
            "intersection_min_keyword": 0.5,
            "intersection_min_vector": 0.65,
            "min_vector_score": 0.55,
            "min_keyword_score": 0.15,
        },
    )
    single_kw = reciprocal_rank_fusion(
        {"keyword": channel_hits["keyword"]},
        weights={"keyword": 1.0},
        rrf_k=60,
        fusion_cfg={"min_keyword_score": 0.15},
    )
    assert dual[uid] > single_kw[uid]


def test_rrf_weak_dual_channel_no_intersection_boost():
    uid = uuid.uuid4()
    channel_hits = {
        "vector": [ChannelHit(unit_id=uid, score=0.56, channel="vector", rank=1)],
        "keyword": [ChannelHit(unit_id=uid, score=0.33, channel="keyword", rank=1)],
    }
    scores = reciprocal_rank_fusion(
        channel_hits,
        weights={"vector": 0.85, "keyword": 1.0},
        rrf_k=60,
        fusion_cfg={
            "intersection_multiplier": 1.5,
            "intersection_min_keyword": 0.5,
            "intersection_min_vector": 0.65,
            "min_vector_score": 0.55,
            "min_keyword_score": 0.15,
        },
    )
    kw_only = reciprocal_rank_fusion(
        {"keyword": channel_hits["keyword"]},
        weights={"keyword": 1.0},
        rrf_k=60,
        fusion_cfg={"min_keyword_score": 0.15},
    )
    vec_only = reciprocal_rank_fusion(
        {"vector": channel_hits["vector"]},
        weights={"vector": 0.85},
        rrf_k=60,
        fusion_cfg={"min_vector_score": 0.55, "single_vector_discount": 1.0},
    )
    assert scores[uid] == pytest.approx(kw_only[uid] + vec_only[uid], rel=1e-3)


def test_rrf_single_vector_discount():
    uid = uuid.uuid4()
    hits = [ChannelHit(unit_id=uid, score=0.60, channel="vector", rank=1)]
    discounted = reciprocal_rank_fusion(
        {"vector": hits},
        weights={"vector": 1.0},
        rrf_k=60,
        fusion_cfg={"min_vector_score": 0.55, "single_vector_discount": 0.5, "high_vector_score": 0.78},
    )
    full = reciprocal_rank_fusion(
        {"vector": hits},
        weights={"vector": 1.0},
        rrf_k=60,
        fusion_cfg={"min_vector_score": 0.55, "single_vector_discount": 1.0, "high_vector_score": 0.78},
    )
    assert discounted[uid] == pytest.approx(full[uid] * 0.5)


def test_fuse_applies_preference_boost():
    asset_id = uuid.uuid4()
    uid = uuid.uuid4()
    unit = _unit(uid, asset_id)
    asset = _asset(asset_id)
    channel_hits = {
        "vector": [
            ChannelHit(
                unit_id=uid,
                score=0.9,
                channel="vector",
                rank=1,
                unit=unit,
                asset=asset,
            )
        ]
    }
    query = RetrievalQuery(
        keywords=["sample"],
        query_text="sample",
        preferences=SearchPreferences(asset_name="test-asset"),
    )
    config = {
        "fusion": {"rrf_k": 60},
        "channels": {"vector": {"weight": 0.85}, "keyword": {"weight": 1.0}, "graph": {"weight": 0.6}},
        "preferences": {"asset_name_boost": 0.12},
    }
    fused = fuse_channel_hits(channel_hits, query, config=config)
    assert fused
    assert fused[0].boosts.get("asset_name") == 0.12
    assert fused[0].final_score > fused[0].rrf_score
    assert fused[0].final_score == pytest.approx(fused[0].rrf_score * (1.0 + sum(fused[0].boosts.values())))
