"""Unit tests for semantic_query vector retrieval."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from database.enums import AssetModality, AssetStatus, ContentType, KgStatus
from database.schemas import AssetRead, ContentUnitRead
from services.retrieval.channels.vector import vector_channel
from services.retrieval.types import RetrievalQuery


def _query(**kwargs) -> RetrievalQuery:
    return RetrievalQuery(keywords=["ignored"], top_k=3, **kwargs)


@pytest.mark.asyncio
async def test_vector_channel_uses_semantic_query(monkeypatch):
    captured: list[str] = []

    def fake_embed(texts):
        captured.extend(texts)
        return [[0.1] * 1024]

    async def fake_vector_search(*args, **kwargs):
        return []

    monkeypatch.setattr("services.retrieval.channels.vector.embed_texts", fake_embed)

    class FakeRepo:
        async def vector_search(self, *args, **kwargs):
            return []

        async def load_assets_for_units(self, unit_ids):
            return {}

    class FakeSession:
        pass

    monkeypatch.setattr("services.retrieval.channels.vector.ContentUnitRepo", lambda session: FakeRepo())

    await vector_channel(
        FakeSession(),
        _query(
            query_text="keyword only",
            semantic_query="What is virtual memory paging?",
        ),
        config={"channels": {"vector": {"enabled": True}}, "candidate_multiplier": 5},
    )
    assert captured == ["What is virtual memory paging?"]
