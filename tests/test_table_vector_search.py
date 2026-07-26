"""Acceptance checks for table content retrieval after PDF ingest."""

from __future__ import annotations

import importlib.util

import pytest
from sqlalchemy import func, select

from database.enums import ContentType
from database.models import ContentUnit
from database.repositories import ContentUnitRepo
from database.session import get_session
from services.ingest.embed import embed_texts


def _sentence_transformers_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


@pytest.mark.skipif(
    not _sentence_transformers_available(),
    reason="sentence-transformers not installed (pip install sentence-transformers)",
)
@pytest.mark.asyncio
async def test_table_content_vector_search() -> None:
    query = "AutoRE-Vicuna-7B"
    query_vec = embed_texts([query])[0]

    async with get_session() as session:
        repo = ContentUnitRepo(session)
        hits = await repo.vector_search(query_vec, limit=5)
        table_count = await session.scalar(
            select(func.count())
            .select_from(ContentUnit)
            .where(
                ContentUnit.content_type == ContentType.TABLE,
                ContentUnit.search_text.ilike("%AutoRE-Vicuna-7B%"),
            )
        )

    assert table_count and table_count >= 1
    assert any(hit.unit.content_type == ContentType.TABLE for hit in hits)
