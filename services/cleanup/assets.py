"""Asset cleanup: orphan scan and delete."""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from core.assets_manager import get_assets_manager
from database.repositories import AssetRepo
from database.schemas import AssetRead
from database.session import get_session
from paths import PROJECT_ROOT
from services.cleanup.types import CleanupReport

logger = logging.getLogger("AssetCleanup")

_TEST_NAME_PATTERNS = (
    re.compile(r"^test\.(pdf|mp4|wav|mp3|mov)$", re.I),
    re.compile(r"persist-test", re.I),
    re.compile(r"unit-test", re.I),
    re.compile(r"^integration\.pdf$", re.I),
    re.compile(r"^age-test\.pdf$", re.I),
)


def raw_file_exists(asset: AssetRead) -> bool:
    path = PROJECT_ROOT / asset.raw_path
    if path.is_file():
        return True
    # Legacy bare filename (pre-fix ingest) under modality folder
    modality = asset.modality.value
    candidate = PROJECT_ROOT / "storage" / "assets" / "raw" / modality / Path(asset.raw_path).name
    return candidate.is_file()


def is_test_asset_name(name: str) -> bool:
    return any(p.search(name) for p in _TEST_NAME_PATTERNS)


async def find_orphan_candidates(*, include_test_names: bool = True) -> list[AssetRead]:
    async with get_session() as session:
        assets = await AssetRepo(session).list_all()
    candidates: list[AssetRead] = []
    for asset in assets:
        if not raw_file_exists(asset) or (include_test_names and is_test_asset_name(asset.name)):
            candidates.append(asset)
    return candidates


def _is_pipeline_active(asset_id: uuid.UUID) -> bool:
    manager = get_assets_manager()
    return asset_id in manager._active


async def delete_asset_record(
    asset_id: uuid.UUID,
    *,
    include_disk: bool = False,
    force: bool = False,
) -> bool:
    if not force and _is_pipeline_active(asset_id):
        return False

    async with get_session() as session:
        repo = AssetRepo(session)
        asset = await repo.get_by_id(asset_id)
        if asset is None:
            return False
        raw_path = asset.raw_path
        processed_path = asset.processed_path
        deleted = await repo.delete(asset_id)

    if not deleted:
        return False

    if include_disk:
        for rel in (raw_path, processed_path):
            if not rel:
                continue
            path = PROJECT_ROOT / rel
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    try:
        from services.kg.age_client import AgeClient

        client = AgeClient()
        await client.delete_asset_subgraph(asset_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("KG subgraph delete failed for %s: %s", asset_id, exc)

    return True


async def cleanup_orphan_assets(
    *,
    dry_run: bool = True,
    include_disk: bool = False,
) -> CleanupReport:
    report = CleanupReport()
    candidates = await find_orphan_candidates()
    report.scanned = len(candidates)

    for asset in candidates:
        if dry_run:
            report.deleted_ids.append(str(asset.id))
            report.deleted += 1
            continue
        try:
            ok = await delete_asset_record(asset.id, include_disk=include_disk)
            if ok:
                report.deleted += 1
                report.deleted_ids.append(str(asset.id))
            else:
                report.skipped += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"{asset.id}: {exc}")
            report.skipped += 1

    if dry_run:
        report.deleted = len(report.deleted_ids)

    return report
