"""Integration tests for audio ingest."""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.session import get_session
from services.ingest.ingest_assets import ingest_processed_dir

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_AUDIO_ROOT = PROJECT_ROOT / "storage/assets/processed/audio"


def _fake_vector(seed: float) -> list[float]:
    values = [math.sin(seed * (index + 1)) for index in range(1024)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _mock_embed(texts: list[str]) -> list[list[float]]:
    return [_fake_vector(float(index + 1)) for index in range(len(texts))]


def _find_audio_processed_dir() -> Path | None:
    if not PROCESSED_AUDIO_ROOT.is_dir():
        return None
    for path in sorted(PROCESSED_AUDIO_ROOT.iterdir()):
        if path.is_dir() and (path / "meta.json").is_file():
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            if meta.get("status") == "success" and meta.get("modality") == "audio":
                return path
    return None


@pytest.mark.skipif(_find_audio_processed_dir() is None, reason="processed audio sample not present")
@pytest.mark.asyncio
async def test_ingest_audio_creates_transcript_units() -> None:
    processed_dir = _find_audio_processed_dir()
    assert processed_dir is not None

    with patch("services.ingest.ingest_assets.embed_texts", side_effect=_mock_embed):
        summary = await ingest_processed_dir(processed_dir, force=True, skip_if_ready=True)

    assert summary["modality"] == "audio"
    assert summary["unit_count"] > 0
    assert summary["transcript_units"] == summary["unit_count"]
    assert summary["coverage"]["units_by_type"]["transcript"] == summary["unit_count"]

    meta = json.loads((processed_dir / "meta.json").read_text(encoding="utf-8"))
    source_hash = (meta.get("fingerprint") or {}).get("source_sha256")

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)
        asset = await asset_repo.get_by_file_hash(source_hash) if source_hash else None
        assert asset is not None
        assert asset.modality == AssetModality.AUDIO
        assert asset.status == AssetStatus.READY
        units = await unit_repo.list_by_asset(asset.id)
        assert units
        assert all(unit.content_type == ContentType.TRANSCRIPT for unit in units)
        await asset_repo.delete(asset.id)
