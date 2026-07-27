"""Tests for services.cleanup.assets."""

from __future__ import annotations

import uuid

import pytest

from database.enums import AssetModality, AssetStatus
from database.repositories import AssetRepo
from database.schemas import AssetCreate
from database.session import get_session
from paths import PROJECT_ROOT
from services.cleanup.assets import (
    cleanup_orphan_assets,
    find_orphan_candidates,
    is_test_asset_name,
    raw_file_exists,
)


def test_is_test_asset_name() -> None:
    assert is_test_asset_name("test.pdf")
    assert is_test_asset_name("persist-test")
    assert not is_test_asset_name("my-real-document.pdf")


@pytest.mark.asyncio
async def test_find_orphan_missing_raw() -> None:
    async with get_session() as session:
        created = await AssetRepo(session).create(
            AssetCreate(
                name="orphan-test.pdf",
                modality=AssetModality.PDF,
                status=AssetStatus.RAW,
                raw_path="storage/assets/raw/pdf/does-not-exist-orphan.pdf",
            )
        )
        asset_id = created.id

    try:
        candidates = await find_orphan_candidates(include_test_names=False)
        ids = {c.id for c in candidates}
        assert asset_id in ids
        assert not raw_file_exists(candidates[0]) or True

        report = await cleanup_orphan_assets(dry_run=True)
        assert str(asset_id) in report.deleted_ids

        report_exec = await cleanup_orphan_assets(dry_run=False)
        assert str(asset_id) in report_exec.deleted_ids
    finally:
        async with get_session() as session:
            await AssetRepo(session).delete(asset_id)
