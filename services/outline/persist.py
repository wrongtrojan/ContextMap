"""Outline persistence: PostgreSQL upsert and optional JSON export."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AssetStatus
from database.repositories import AssetRepo, OutlineRepo
from database.schemas import OutlineCreate, OutlineRead


def default_export_filename(config: dict[str, Any] | None = None) -> str:
    persist_cfg = (config or {}).get("persist") or {}
    return str(persist_cfg.get("export_filename", "summary_outline.json"))


def should_export_json(*, config: dict[str, Any], cli_export: bool | None = None) -> bool:
    if cli_export is not None:
        return cli_export
    persist_cfg = config.get("persist") or {}
    return bool(persist_cfg.get("export_json", False))


def export_outline_json(
    processed_dir: Path,
    *,
    asset_id: uuid.UUID,
    title: str | None,
    tree: list[dict[str, Any]],
    model_id: str | None,
    filename: str = "summary_outline.json",
) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)
    export_path = processed_dir / filename
    payload = {
        "asset_id": str(asset_id),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "title": title,
        "model_id": model_id,
        "outline": {
            "title": title,
            "outline": tree,
        },
    }
    export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return export_path


def load_outline_json_fallback(processed_dir: Path, filename: str = "summary_outline.json") -> dict[str, Any] | None:
    export_path = processed_dir / filename
    if not export_path.is_file():
        return None
    try:
        return json.loads(export_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def outline_to_api_payload(outline: OutlineRead) -> dict[str, Any]:
    return {
        "asset_id": str(outline.asset_id),
        "generated_at": outline.generated_at.isoformat(),
        "title": outline.title,
        "model_id": outline.model_id,
        "outline": {
            "title": outline.title,
            "outline": outline.tree,
        },
    }


async def persist_outline(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    title: str | None,
    tree: list[dict[str, Any]],
    model_id: str | None,
    outline_fingerprint: dict[str, Any],
) -> OutlineRead:
    asset_repo = AssetRepo(session)
    outline_repo = OutlineRepo(session)
    outline = await outline_repo.upsert(
        OutlineCreate(
            asset_id=asset_id,
            title=title,
            tree=tree,
            model_id=model_id,
        )
    )
    metadata = {"outline_fingerprint": outline_fingerprint}
    current = await asset_repo.get_by_id(asset_id)
    if current is not None and current.status != AssetStatus.INGESTING:
        await asset_repo.update_on_ingest(
            asset_id,
            name=current.name,
            raw_path=current.raw_path,
            processed_path=current.processed_path,
            file_size_bytes=current.file_size_bytes,
            metadata=metadata,
            status=AssetStatus.READY,
        )
    elif current is not None:
        await asset_repo.update_on_ingest(
            asset_id,
            name=current.name,
            raw_path=current.raw_path,
            processed_path=current.processed_path,
            file_size_bytes=current.file_size_bytes,
            metadata=metadata,
            status=current.status,
        )
    return outline
