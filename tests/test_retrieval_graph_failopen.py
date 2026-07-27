"""Graph channel fail-open behavior."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, ContentUnitCreate
from database.session import get_session
from services.retrieval.prepare import parse_search_needs
from services.retrieval.search import hybrid_search
from tests.helpers.mock_vectors import fake_vector


@pytest.mark.asyncio
async def test_hybrid_search_graph_skipped_when_kg_disabled():
    query_vector = fake_vector(2.0)

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)

        asset = await asset_repo.create(
            AssetCreate(
                name="graph-failopen-asset",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/test.pdf",
                processed_path="storage/assets/processed/pdf/test",
                file_hash=f"graph-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
            )
        )
        await unit_repo.bulk_create(
            [
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TEXT,
                    search_text="Transformer attention mechanism for NLP tasks.",
                    content_ref="Transformer attention mechanism for NLP tasks.",
                    embedding=query_vector,
                    timestamp_anchor=1.0,
                    chunk_index=0,
                )
            ]
        )

        search_needs = {
            "search_params": {"keywords": ["Transformer", "attention"], "top_k": 5},
            "preferences": {"asset_name": None, "modality": None, "timestamp": None},
        }
        config = {
            "top_k_default": 5,
            "candidate_multiplier": 2,
            "channels": {
                "vector": {"enabled": True, "weight": 1.0},
                "keyword": {"enabled": True, "weight": 0.8},
                "graph": {"enabled": True, "weight": 0.6, "fail_open": True, "depth": 2, "entity_limit": 10},
            },
            "fusion": {"method": "rrf", "rrf_k": 60},
            "dedup": {"text_normalize": True, "time_window_sec": 30, "mmr_lambda": 0.7, "mmr_pool_multiplier": 2},
            "preferences": {},
            "filters": {"asset_status": "ready"},
        }

        with patch("services.retrieval.channels.graph.load_kg_config", return_value={"enabled": False}):
            response = await hybrid_search(session, search_needs=search_needs, config=config)

        assert response["status"] == "success"
        assert response["results"]
        assert response["debug"]["graph_skipped"] is True
        assert response["debug"]["graph_skip_reason"] == "kg.disabled"

        await asset_repo.delete(asset.id)


@pytest.mark.asyncio
async def test_hybrid_search_graph_error_fail_open():
    search_needs = {
        "search_params": {"keywords": ["test"], "top_k": 3},
        "preferences": {},
    }
    config = {
        "top_k_default": 3,
        "candidate_multiplier": 2,
        "channels": {
            "vector": {"enabled": False, "weight": 1.0},
            "keyword": {"enabled": False, "weight": 0.8},
            "graph": {"enabled": True, "weight": 0.6, "fail_open": True},
        },
        "fusion": {"rrf_k": 60},
        "dedup": {},
        "preferences": {},
        "filters": {},
    }

    async with get_session() as session:
        with patch("services.retrieval.channels.graph.load_kg_config", return_value={"enabled": True}):
            with patch(
                "services.retrieval.search.graph_channel",
                new=AsyncMock(side_effect=RuntimeError("AGE unavailable")),
            ):
                response = await hybrid_search(session, search_needs=search_needs, config=config)

    assert response["status"] == "success"
    assert response["debug"]["graph_error"] is not None


def test_parse_search_needs():
    query = parse_search_needs(
        {
            "search_params": {
                "keywords": ["a", "b"],
                "semantic_query": "find a and b in the document",
                "top_k": 4,
            },
            "preferences": {"asset_name": "book", "modality": "pdf", "timestamp": 2},
        }
    )
    assert query.keywords == ["a", "b"]
    assert query.top_k == 4
    assert query.query_text == "a b"
    assert query.semantic_query == "find a and b in the document"
    assert query.preferences.asset_name == "book"
