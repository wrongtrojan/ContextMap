"""Evidence formatting tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from database.enums import AssetModality, AssetStatus, ContentType, KgStatus
from database.schemas import AssetRead, ContentUnitRead
from services.retrieval.format import format_evidence
from services.retrieval.types import ScoredHit


def _scored_hit(modality: AssetModality, content_type: ContentType) -> ScoredHit:
    uid = uuid.uuid4()
    aid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    return ScoredHit(
        unit_id=uid,
        unit=ContentUnitRead(
            id=uid,
            asset_id=aid,
            content_type=content_type,
            search_text="caption text",
            content_ref="body text",
            embedding=None,
            timestamp_anchor=3.0,
            chunk_index=0,
            metadata_={"page_label": 3, "block_type": "title"},
            created_at=now,
        ),
        asset=AssetRead(
            id=aid,
            name="math-book",
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
        final_score=1.5,
        rrf_score=1.0,
        vector_score=0.9,
        sources=["vector"],
    )


def test_format_pdf_evidence():
    hit = _scored_hit(AssetModality.PDF, ContentType.TEXT)
    evidence = format_evidence(hit, rank=0)
    assert evidence["content"] == "body text"
    assert evidence["metadata"]["page_label"] == 3
    assert evidence["metadata"]["timestamp"] is None
    assert evidence["metadata"]["asset_name"] == "math-book"
    assert "content_unit_id" in evidence


def test_format_video_frame_uses_search_text():
    hit = _scored_hit(AssetModality.VIDEO, ContentType.FRAME)
    evidence = format_evidence(hit, rank=1)
    assert evidence["content"] == "caption text"
    assert evidence["metadata"]["timestamp"] == 3.0
    assert evidence["metadata"]["rank"] == 1
