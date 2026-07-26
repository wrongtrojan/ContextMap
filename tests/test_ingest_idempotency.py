"""Integration tests for ingest idempotency (skip, force, MinIO order, failure state)."""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate
from database.session import get_session
from services.common.versions import LOADER_VERSION
from services.ingest.fingerprint import (
    build_ingest_fingerprint,
    ingest_fingerprints_match,
)
from services.ingest.ingest_assets import (
    _should_skip_ingest,
    ingest_processed_dir,
    repair_minio_for_processed_dir,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_DIR = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
)


def _fake_vector(seed: float) -> list[float]:
    values = [math.sin(seed * (index + 1)) for index in range(1024)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _mock_embed(texts: list[str]) -> list[list[float]]:
    return [_fake_vector(float(index + 1)) for index in range(len(texts))]


def _mock_minio_upload(*_args, **_kwargs) -> None:
    return None


def _ready_asset(metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=AssetStatus.READY,
        metadata=metadata,
    )


def test_ingest_fingerprint_match_requires_all_fields() -> None:
    current = {
        "middle_json_mtime": 1,
        "middle_json_size": 100,
        "loader_version": LOADER_VERSION,
        "unit_count_by_type": {"text": 1},
        "parse_parsed_at": "2026-01-01T00:00:00Z",
    }
    assert ingest_fingerprints_match(current, dict(current))
    changed = dict(current)
    changed["unit_count_by_type"] = {"text": 2}
    assert not ingest_fingerprints_match(current, changed)


def test_should_skip_ingest_cache_hit() -> None:
    fp = {
        "middle_json_mtime": 1,
        "middle_json_size": 1,
        "loader_version": LOADER_VERSION,
        "unit_count_by_type": {"text": 1},
        "parse_parsed_at": "t",
    }
    asset = _ready_asset({"ingest_fingerprint": fp})
    skip, reason = _should_skip_ingest(asset, fp, force=False, skip_if_ready=True)
    assert skip is True
    assert reason == "cache_hit"


def test_should_skip_ingest_force() -> None:
    fp = {"loader_version": LOADER_VERSION}
    asset = _ready_asset({"ingest_fingerprint": fp})
    skip, reason = _should_skip_ingest(asset, fp, force=True, skip_if_ready=True)
    assert skip is False
    assert reason == "force"


@pytest.mark.asyncio
async def test_mark_failed_increments_retry_count() -> None:
    async with get_session() as session:
        repo = AssetRepo(session)
        asset = await repo.create(
            AssetCreate(
                name="fail-test",
                modality=AssetModality.AUDIO,
                raw_path="storage/assets/raw/audio/x.wav",
                processed_path="storage/assets/processed/audio/x",
                file_hash=f"fail-{uuid.uuid4().hex}",
                status=AssetStatus.INGESTING,
            )
        )
        await repo.mark_failed(asset.id, "boom")
        refreshed = await repo.get_by_id(asset.id)
        assert refreshed is not None
        assert refreshed.status == AssetStatus.FAILED
        assert refreshed.error_message == "boom"
        assert refreshed.retry_count == 1
        await repo.delete(asset.id)


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
@pytest.mark.asyncio
async def test_ingest_idempotency_flow() -> None:
    with (
        patch("services.ingest.ingest_assets.embed_texts", side_effect=_mock_embed),
        patch("services.ingest.ingest_assets.upload_file", side_effect=_mock_minio_upload),
        patch("services.ingest.ingest_assets.delete_prefix", return_value=0) as mock_delete,
    ):
        first = await ingest_processed_dir(AUTORE_DIR, force=True, skip_if_ready=True)
        assert first["action"] in {"created", "reingested"}

        second = await ingest_processed_dir(AUTORE_DIR, force=False, skip_if_ready=True)
        assert second["action"] == "skipped"
        assert second["skip_reason"] == "cache_hit"

        mock_delete.reset_mock()
        forced = await ingest_processed_dir(AUTORE_DIR, force=True, skip_if_ready=True)
        assert forced["action"] == "reingested"
        assert mock_delete.called

        asset_id = uuid.UUID(forced["asset_id"])
        repair = await repair_minio_for_processed_dir(AUTORE_DIR)
        assert repair["action"] == "repair_minio"

        async with get_session() as session:
            units = await ContentUnitRepo(session).list_by_asset(asset_id)
            minio_units = [
                unit
                for unit in units
                if unit.content_type in {ContentType.IMAGE, ContentType.TABLE, ContentType.FRAME}
            ]
            for unit in minio_units:
                if unit.metadata.get("minio_key"):
                    assert unit.content_ref.startswith("pdf/")


def test_ingest_commits_db_before_minio_upload() -> None:
    import inspect

    source = inspect.getsource(ingest_processed_dir)
    assert source.index("bulk_create") < source.index("_apply_minio_uploads")


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
@pytest.mark.asyncio
async def test_minio_failure_marks_asset_failed() -> None:
    with (
        patch("services.ingest.ingest_assets.embed_texts", side_effect=_mock_embed),
        patch("services.ingest.ingest_assets._apply_minio_uploads", side_effect=RuntimeError("MinIO upload failed")),
        patch("services.ingest.ingest_assets.delete_prefix", return_value=0),
    ):
        with pytest.raises(RuntimeError, match="MinIO upload failed"):
            await ingest_processed_dir(AUTORE_DIR, force=True, skip_if_ready=False)

    meta = __import__("json").loads((AUTORE_DIR / "meta.json").read_text(encoding="utf-8"))
    file_hash = (meta.get("fingerprint") or {}).get("pdf_sha256")
    async with get_session() as session:
        asset = await AssetRepo(session).get_by_file_hash(file_hash)
        assert asset is not None
        assert asset.status == AssetStatus.FAILED
        assert asset.error_message is not None


@pytest.mark.skipif(not (AUTORE_DIR / "meta.json").exists(), reason="AutoRE sample not present")
def test_build_ingest_fingerprint_from_autore() -> None:
    import json

    meta = json.loads((AUTORE_DIR / "meta.json").read_text(encoding="utf-8"))
    middle = next(AUTORE_DIR.glob("*_middle.json"))
    fp = build_ingest_fingerprint(meta, middle, {"units_by_type": {"text": 90, "table": 7}})
    assert fp["loader_version"] == LOADER_VERSION
    assert fp["unit_count_by_type"]["table"] == 7
