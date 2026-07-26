"""End-to-end KG extraction smoke test (mock or real AutoRE)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text

from database.enums import AssetStatus, ContentType, KgStatus
from database.models import Asset, ContentUnit
from database.session import dispose_engine, get_session


AUTORE_ASSET_ID = uuid.UUID("e14b8f2d-ce1a-4666-8472-4a1b28e8dfa9")


async def _age_available() -> bool:
    try:
        async with get_session() as session:
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'age'")
            )
            return result.scalar_one_or_none() == 1
    except Exception:
        return False


@pytest.fixture
async def age_ready():
    await dispose_engine()
    if not await _age_available():
        pytest.skip("Apache AGE extension not available — rebuild postgres image")
    yield
    await dispose_engine()


@pytest.mark.asyncio
async def test_kg_e2e_mock_autore_pdf(age_ready):
    from services.kg.extract_assets import extract_kg_for_asset

    async with get_session() as session:
        asset = await session.get(Asset, AUTORE_ASSET_ID)
        if asset is None:
            pytest.skip("AutoRE sample asset not ingested")
        unit_count = await session.scalar(
            select(func.count())
            .select_from(ContentUnit)
            .where(
                ContentUnit.asset_id == AUTORE_ASSET_ID,
                ContentUnit.content_type == ContentType.TEXT,
            )
        )
    if not unit_count or unit_count < 10:
        pytest.skip("AutoRE asset has insufficient text units")

    summary = await extract_kg_for_asset(AUTORE_ASSET_ID, use_mock=True)
    assert summary["kg_status"] in {KgStatus.READY.value, KgStatus.PARTIAL.value}
    assert summary["triples_extracted"] >= 1

    async with get_session() as session:
        asset = await session.get(Asset, AUTORE_ASSET_ID)
        assert asset is not None
        assert asset.kg_status in {KgStatus.READY, KgStatus.PARTIAL}
        assert asset.triple_count >= 1
        assert asset.status == AssetStatus.READY

        from services.kg.age_client import AgeClient

        graph = await AgeClient(session).subgraph_by_asset(AUTORE_ASSET_ID, depth=1)
        assert graph.get("asset_id") == str(AUTORE_ASSET_ID)
