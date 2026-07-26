import uuid

import pytest
from sqlalchemy import text

from database.session import dispose_engine, get_session


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
        pytest.skip("Apache AGE extension not available")
    yield
    await dispose_engine()


@pytest.mark.asyncio
async def test_age_client_write_and_search(age_ready):
    from database.repositories import AssetRepo
    from database.schemas import AssetCreate
    from database.enums import AssetModality, AssetStatus
    from services.kg.age_client import AgeClient
    from services.kg.types import TextChunk, Triple

    asset_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    async with get_session() as session:
        await AssetRepo(session).create(
            AssetCreate(
                name="age-test",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/age-test.pdf",
                status=AssetStatus.RAW,
            ),
            asset_id=asset_id,
        )
        client = AgeClient(session)
        count = await client.write_asset_graph(
            asset_id=asset_id,
            asset_name="age-test",
            modality="pdf",
            chunks=[
                TextChunk(
                    text="AutoRE performs document-level relation extraction.",
                    source_unit_id=unit_id,
                    asset_id=asset_id,
                    modality="pdf",
                )
            ],
            triples=[
                Triple(
                    head="AutoRE",
                    relation="performs",
                    tail="relation extraction",
                    source_unit_id=unit_id,
                    source_modality="pdf",
                )
            ],
        )
        assert count == 1
        hits = await client.search_entities("autore", asset_id=asset_id)
        assert hits
        await AssetRepo(session).delete(asset_id)
