"""Integration tests for hybrid retrieval."""

from __future__ import annotations

import uuid

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, ContentUnitCreate
from database.session import get_session
from services.retrieval.search import hybrid_search
from tests.helpers.mock_vectors import fake_vector


@pytest.mark.asyncio
async def test_hybrid_search_vector_and_keyword():
    target_vector = fake_vector(5.0)
    other_vector = fake_vector(88.0)

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)

        asset = await asset_repo.create(
            AssetCreate(
                name="integration-retrieval-asset",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/integration.pdf",
                processed_path="storage/assets/processed/pdf/integration",
                file_hash=f"integration-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
            )
        )
        await unit_repo.bulk_create(
            [
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TEXT,
                    search_text="Graph neural networks learn relational structure.",
                    content_ref="Graph neural networks learn relational structure.",
                    embedding=target_vector,
                    timestamp_anchor=1.0,
                    chunk_index=0,
                ),
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TEXT,
                    search_text="Cooking pasta with tomato sauce.",
                    content_ref="Cooking pasta with tomato sauce.",
                    embedding=other_vector,
                    timestamp_anchor=2.0,
                    chunk_index=1,
                ),
            ]
        )

        search_needs = {
            "search_params": {"keywords": ["Graph", "networks"], "top_k": 3},
            "preferences": {"asset_name": "integration-retrieval", "modality": "pdf", "timestamp": None},
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "services.retrieval.channels.vector.embed_texts",
                lambda texts: [target_vector],
            )
            mp.setattr(
                "services.retrieval.channels.graph.load_kg_config",
                lambda *args, **kwargs: {"enabled": False},
            )
            response = await hybrid_search(session, search_needs=search_needs)

        assert response["status"] == "success"
        assert response["results"]
        top = response["results"][0]
        assert "Graph neural" in top["content"]
        assert top["metadata"]["asset_id"] == str(asset.id)
        assert "vector" in top["metadata"]["sources"] or "keyword" in top["metadata"]["sources"]

        await asset_repo.delete(asset.id)


@pytest.mark.asyncio
async def test_asset_repo_find_by_name_ilike():
    async with get_session() as session:
        asset_repo = AssetRepo(session)
        asset = await asset_repo.create(
            AssetCreate(
                name="Unique Book Title Alpha",
                modality=AssetModality.PDF,
                raw_path="raw",
                file_hash=f"find-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
            )
        )
        matches = await asset_repo.find_by_name_ilike("Book Title")
        assert matches
        assert matches[0].id == asset.id
        await asset_repo.delete(asset.id)
