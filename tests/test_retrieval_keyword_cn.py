"""Integration tests for Chinese keyword search."""

from __future__ import annotations

import uuid

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, ContentUnitCreate
from database.session import get_session
from services.common.text_segment import segment_for_fts


@pytest.mark.asyncio
async def test_keyword_search_chinese_tokens():
    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)

        asset = await asset_repo.create(
            AssetCreate(
                name="csapp-cn-test",
                modality=AssetModality.AUDIO,
                raw_path="raw/audio/test.m4a",
                file_hash=f"cn-kw-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
            )
        )
        text = "这一节我们讲解虚拟内存的页表结构与地址翻译机制。"
        tokens = segment_for_fts(text)
        await unit_repo.bulk_create(
            [
                ContentUnitCreate(
                    asset_id=asset.id,
                    content_type=ContentType.TRANSCRIPT,
                    search_text=text,
                    search_tokens=tokens,
                    content_ref=text,
                    timestamp_anchor=10.0,
                    chunk_index=0,
                )
            ]
        )

        hits = await unit_repo.keyword_search(
            query_text="虚拟内存",
            keywords=["虚拟内存"],
            limit=5,
            segment_chinese=True,
        )
        assert hits
        assert hits[0].unit.search_text == text

        await asset_repo.delete(asset.id)
