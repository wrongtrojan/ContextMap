"""Test helpers for resolving assets without creating duplicates."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from database.enums import AssetModality, AssetStatus
from database.repositories import AssetRepo
from database.schemas import AssetCreate
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.processed_assets import file_hash as meta_file_hash


async def resolve_asset_for_processed_dir(
    session: AsyncSession,
    processed_dir: Path,
    *,
    project_root: Path,
    modality: AssetModality = AssetModality.PDF,
    create_if_missing: bool = True,
    create_status: AssetStatus = AssetStatus.READY,
) -> uuid.UUID | None:
    """Find an asset by processed_path or file_hash; optionally create one."""
    asset_repo = AssetRepo(session)
    processed_path = str(processed_dir.relative_to(project_root))

    existing = await asset_repo.get_by_processed_path(processed_path)
    if existing is not None:
        return existing.id

    source_hash: str | None = None
    meta_path = processed_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        source_hash = meta_file_hash(meta)

    if source_hash:
        by_hash = await asset_repo.get_by_file_hash(source_hash)
        if by_hash is not None:
            return by_hash.id

    if not create_if_missing:
        return None

    created = await asset_repo.create(
        AssetCreate(
            name=processed_dir.name,
            modality=modality,
            raw_path=f"storage/assets/raw/{modality.value}/test.pdf",
            processed_path=processed_path,
            file_hash=source_hash or f"test-{uuid.uuid4().hex}",
            status=create_status,
        )
    )
    return created.id
