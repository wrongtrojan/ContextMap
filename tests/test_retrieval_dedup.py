"""Unit tests for retrieval deduplication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from database.enums import AssetModality, AssetStatus, ContentType, KgStatus
from database.schemas import AssetRead, ContentUnitRead
from services.retrieval.dedup import deduplicate_and_rank, normalize_text, protect_keyword_hits
from services.retrieval.types import ScoredHit


def _hit(
    *,
    unit_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    search_text: str = "hello world",
    timestamp: float = 0.0,
    score: float = 1.0,
    embedding: list[float] | None = None,
    modality: AssetModality = AssetModality.VIDEO,
    chunk_index: int = 0,
) -> ScoredHit:
    uid = unit_id or uuid.uuid4()
    aid = asset_id or uuid.uuid4()
    now = datetime.now(timezone.utc)
    return ScoredHit(
        unit_id=uid,
        unit=ContentUnitRead(
            id=uid,
            asset_id=aid,
            content_type=ContentType.TRANSCRIPT,
            search_text=search_text,
            content_ref=search_text,
            embedding=embedding,
            timestamp_anchor=timestamp,
            chunk_index=chunk_index,
            metadata_={},
            created_at=now,
        ),
        asset=AssetRead(
            id=aid,
            name="video",
            modality=modality,
            status=AssetStatus.READY,
            kg_status=KgStatus.SKIPPED,
            raw_path="raw",
            processed_path="processed",
            file_size_bytes=1,
            file_hash="x",
            retry_count=0,
            triple_count=0,
            error_message=None,
            metadata_={},
            created_at=now,
            updated_at=now,
        ),
        final_score=score,
        rrf_score=score,
    )


def test_normalize_text():
    assert normalize_text("  Hello   World ") == "hello world"


def test_dedup_exact_id():
    uid = uuid.uuid4()
    hits = [_hit(unit_id=uid, score=2.0), _hit(unit_id=uid, score=1.0)]
    result, stats = deduplicate_and_rank(hits, top_k=5, config={"dedup": {}})
    assert len(result) == 1
    assert stats["exact_id"] == 1


def test_dedup_structural_same_timestamp_bucket():
    asset_id = uuid.uuid4()
    hits = [
        _hit(asset_id=asset_id, search_text="a", timestamp=10.0, score=2.0),
        _hit(asset_id=asset_id, search_text="b", timestamp=12.0, score=1.0),
    ]
    result, stats = deduplicate_and_rank(hits, top_k=5, config={"dedup": {"time_window_sec": 30}})
    assert len(result) == 1
    assert stats["structural"] == 1


def test_pdf_structural_keeps_different_chunks_on_same_page():
    asset_id = uuid.uuid4()
    hits = [
        _hit(
            asset_id=asset_id,
            search_text="chunk-a",
            timestamp=3.0,
            score=2.0,
            modality=AssetModality.PDF,
            chunk_index=0,
        ),
        _hit(
            asset_id=asset_id,
            search_text="chunk-b",
            timestamp=3.0,
            score=1.5,
            modality=AssetModality.PDF,
            chunk_index=1,
        ),
    ]
    result, stats = deduplicate_and_rank(hits, top_k=5, config={"dedup": {}})
    assert len(result) == 2
    assert stats["structural"] == 0


def test_protect_keyword_hits():
    hits = [
        _hit(search_text="low-kw", score=0.10),
        _hit(search_text="high-kw", score=0.05),
    ]
    hits[0].keyword_score = 0.3
    hits[1].keyword_score = 1.0
    protected, n = protect_keyword_hits(hits, protect_top_n=1, min_keyword_score=0.5)
    assert n == 1
    assert protected[0].keyword_score == 1.0
