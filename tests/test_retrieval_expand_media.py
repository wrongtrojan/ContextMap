"""Tests for expand_linked_media."""

import uuid
from datetime import datetime, timezone

import pytest

from database.enums import AssetModality, AssetStatus, ContentType, KgStatus
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, ContentUnitCreate
from database.session import get_session
from services.retrieval.expand_media import expand_linked_media


@pytest.mark.asyncio
async def test_expand_pdf_text_to_same_page_image():
    asset_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        await AssetRepo(session).create(
            AssetCreate(
                name="book.pdf",
                modality=AssetModality.PDF,
                status=AssetStatus.READY,
                raw_path="raw/book.pdf",
                processed_path="storage/assets/processed/pdf/book",
            )
        )
        # recreate with known id via direct insert workaround - use create then update
        asset = (await AssetRepo(session).find_by_name_ilike("book.pdf", limit=1))[0]
        asset_id = asset.id

        repo = ContentUnitRepo(session)
        text_unit = (
            await repo.bulk_create(
                [
                    ContentUnitCreate(
                        asset_id=asset_id,
                        content_type=ContentType.TEXT,
                        search_text="chapter intro",
                        content_ref="chapter intro",
                        timestamp_anchor=3,
                        chunk_index=0,
                        metadata={"page_label": 3},
                    ),
                    ContentUnitCreate(
                        asset_id=asset_id,
                        content_type=ContentType.IMAGE,
                        search_text="figure caption",
                        content_ref="fig.jpg",
                        timestamp_anchor=3,
                        chunk_index=1,
                        metadata={"page_label": 3, "image_filename": "fig.jpg"},
                    ),
                ]
            )
        )[0]

        evidence = [
            {
                "content_unit_id": str(text_unit.id),
                "content": "chapter intro",
                "metadata": {
                    "asset_id": str(asset_id),
                    "type": "text",
                    "page_label": 3,
                },
            }
        ]
        expanded = await expand_linked_media(session, evidence)
        assert expanded[0].get("linked_media")
        assert expanded[0]["linked_media"][0]["metadata"]["type"] == "image"
