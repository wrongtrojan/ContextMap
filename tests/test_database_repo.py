import math
import uuid

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, ContentUnitCreate
from database.session import get_session


def _fake_vector(seed: float) -> list[float]:
    values = [math.sin(seed * (index + 1)) for index in range(1024)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


@pytest.mark.asyncio
async def test_asset_and_vector_search():
    query_vector = _fake_vector(1.0)
    other_vector = _fake_vector(99.0)

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)

        asset = await asset_repo.create(
            AssetCreate(
                name="test-asset",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/test.pdf",
                processed_path="storage/assets/processed/pdf/test",
                file_hash=f"test-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
            )
        )

        units = await unit_repo.bulk_create(
            [
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TEXT,
                    search_text="AutoRE performs document-level relation extraction with LLMs.",
                    content_ref="AutoRE performs document-level relation extraction with LLMs.",
                    embedding=query_vector,
                    timestamp_anchor=1.0,
                    chunk_index=0,
                ),
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TEXT,
                    search_text="Unrelated content about cooking recipes.",
                    content_ref="Unrelated content about cooking recipes.",
                    embedding=other_vector,
                    timestamp_anchor=2.0,
                    chunk_index=1,
                ),
            ]
        )

        assert len(units) == 2
        hits = await unit_repo.vector_search(query_vector, limit=1, asset_id=asset.id)
        assert hits
        assert "relation extraction" in hits[0].unit.search_text.lower()

        await asset_repo.delete(asset.id)
