import uuid

import pytest

from database.enums import ContentType
from database.schemas import ContentUnitRead
from datetime import datetime, timezone

from services.kg.chunker import units_to_chunks


def _unit(text: str, *, chunk_index: int = 0, content_type: ContentType = ContentType.TEXT) -> ContentUnitRead:
    now = datetime.now(timezone.utc)
    return ContentUnitRead(
        id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        content_type=content_type,
        search_text=text,
        content_ref=text,
        embedding=None,
        timestamp_anchor=0.0,
        chunk_index=chunk_index,
        metadata_={},
        created_at=now,
    )


def test_units_to_chunks_splits_long_text():
    asset_id = uuid.uuid4()
    long_text = "第一句。" * 200
    chunks = units_to_chunks([_unit(long_text)], asset_id=asset_id, modality="pdf", max_tokens=64)
    assert len(chunks) > 1
    assert all(chunk.asset_id == asset_id for chunk in chunks)


def test_units_to_chunks_includes_transcript():
    asset_id = uuid.uuid4()
    chunks = units_to_chunks(
        [_unit("讲解内容。", content_type=ContentType.TRANSCRIPT)],
        asset_id=asset_id,
        modality="audio",
    )
    assert len(chunks) == 1
    assert chunks[0].modality == "audio"
