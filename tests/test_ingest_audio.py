"""Integration tests for audio ingest."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.session import get_session
from services.ingest.ingest_assets import ingest_processed_dir
from tests.helpers.corpus_paths import find_audio_processed_dir
from tests.helpers.ingest_fixtures import copy_processed_dir_for_test, delete_asset_by_file_hash
from tests.helpers.mock_vectors import mock_embed_texts


@pytest.mark.skipif(find_audio_processed_dir() is None, reason="processed audio sample not present")
@pytest.mark.asyncio
async def test_ingest_audio_creates_transcript_units(tmp_path: Path) -> None:
    source_dir = find_audio_processed_dir()
    assert source_dir is not None
    processed_dir, test_hash = copy_processed_dir_for_test(
        source_dir,
        tmp_path,
        hash_key="source_sha256",
        prefix="audio-ingest-test",
    )

    try:
        with patch("services.ingest.ingest_assets.embed_texts", side_effect=mock_embed_texts):
            summary = await ingest_processed_dir(processed_dir, force=True, skip_if_ready=True)

        assert summary["modality"] == "audio"
        assert summary["unit_count"] > 0
        assert summary["transcript_units"] == summary["unit_count"]
        assert summary["coverage"]["units_by_type"]["transcript"] == summary["unit_count"]

        async with get_session() as session:
            asset_repo = AssetRepo(session)
            unit_repo = ContentUnitRepo(session)
            asset = await asset_repo.get_by_file_hash(test_hash)
            assert asset is not None
            assert asset.modality == AssetModality.AUDIO
            assert asset.status == AssetStatus.READY
            units = await unit_repo.list_by_asset(asset.id)
            assert units
            assert all(unit.content_type == ContentType.TRANSCRIPT for unit in units)
    finally:
        await delete_asset_by_file_hash(test_hash)
