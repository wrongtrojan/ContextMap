import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from core.assets_manager import get_assets_manager
from database.enums import AssetStatus
from database.repositories import AssetRepo, OutlineRepo
from database.session import get_session
from paths import PROJECT_ROOT
from services.outline.llm import load_outline_config
from services.outline.persist import (
    default_export_filename,
    load_outline_json_fallback,
    outline_to_api_payload,
)
from web.api.deps import parse_asset_id

logger = logging.getLogger("AssetsAPI")
router = APIRouter()


async def _load_outline_from_pg(asset_uuid: uuid.UUID) -> dict | None:
    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_uuid)
        if asset is None:
            return None
        outline = await OutlineRepo(session).get_by_asset(asset_uuid)
        if outline is None:
            return None
        return {
            "asset": asset,
            "data": outline_to_api_payload(outline),
        }


def _load_outline_from_file(processed_path: str | None) -> dict | None:
    if not processed_path:
        return None
    config = load_outline_config()
    filename = default_export_filename(config)
    processed_dir = PROJECT_ROOT / processed_path
    return load_outline_json_fallback(processed_dir, filename=filename)


@router.post("/{asset_id}/retry")
async def retry_asset(asset_id: str):
    asset_uuid = parse_asset_id(asset_id)
    await get_assets_manager().retry(asset_uuid)
    return {"status": "success", "message": "Asset re-enqueued", "asset_id": asset_id}


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, include_disk: bool = Query(True)):
    from services.cleanup.assets import delete_asset_record

    asset_uuid = parse_asset_id(asset_id)
    deleted = await delete_asset_record(asset_uuid, include_disk=include_disk)
    if not deleted:
        raise HTTPException(status_code=409, detail="Asset not found or pipeline active")
    return {"status": "success", "asset_id": asset_id, "include_disk": include_disk}


@router.get("/stream")
async def asset_stream(request: Request, asset_id: str = Query(...)):
    asset_uuid = parse_asset_id(asset_id)

    manager = get_assets_manager()
    queue = manager.event_bus.subscribe(asset_id)

    async def event_generator():
        try:
            async with get_session() as session:
                asset = await AssetRepo(session).get_by_id(asset_uuid)
            if asset is None:
                yield {"event": "error", "data": json.dumps({"message": "Asset not found"})}
                return
            yield {
                "event": "state_change",
                "data": json.dumps({"status": asset.status.value}, ensure_ascii=False),
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                event_type = event.get("type", "message")
                yield {
                    "event": event_type,
                    "data": json.dumps(event, ensure_ascii=False),
                }
                if event_type in {"completed", "error"}:
                    break
        finally:
            manager.event_bus.unsubscribe(asset_id, queue)

    return EventSourceResponse(event_generator())


@router.get("/structure")
async def get_structure(asset_id: str):
    asset_uuid = parse_asset_id(asset_id)

    pg_result = await _load_outline_from_pg(asset_uuid)
    if pg_result is not None:
        asset = pg_result["asset"]
        if asset.status not in {AssetStatus.READY, AssetStatus.INGESTING}:
            return {
                "status": "processing",
                "current_step": asset.status.value,
                "message": "Structure is not generated yet.",
            }
        return {
            "status": "success",
            "data": pg_result["data"],
            "message": "Outline retrieved successfully",
        }

    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_uuid)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.status not in {AssetStatus.READY, AssetStatus.INGESTING}:
        return {
            "status": "processing",
            "current_step": asset.status.value,
            "message": "Structure is not generated yet.",
        }
    file_data = _load_outline_from_file(asset.processed_path)
    if file_data is not None:
        return {
            "status": "success",
            "data": file_data,
            "message": "Outline retrieved successfully (file fallback)",
        }
    raise HTTPException(status_code=404, detail="Outline not found for asset")


@router.get("/media/{filename}")
async def get_processed_media(filename: str):
    """Serve a processed figure/frame by filename (PDF images / video frames)."""
    from pathlib import Path

    from fastapi.responses import FileResponse
    from paths import PROCESSED_AUDIO_DIR, PROCESSED_PDF_DIR, PROCESSED_VIDEO_DIR

    # Prevent path traversal
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename.replace("\\", "/").split("/")[-1]:
        raise HTTPException(status_code=400, detail="Invalid filename")

    search_roots = (PROCESSED_PDF_DIR, PROCESSED_VIDEO_DIR, PROCESSED_AUDIO_DIR)
    for root in search_roots:
        if not root.exists():
            continue
        # Prefer images/ subdir, then any match under the modality root
        for candidate in (
            *root.glob(f"*/images/{safe_name}"),
            *root.glob(f"*/{safe_name}"),
            *root.glob(f"**/{safe_name}"),
        ):
            if candidate.is_file():
                return FileResponse(candidate)

    raise HTTPException(status_code=404, detail=f"Media not found: {safe_name}")


@router.get("/preview")
async def get_preview(asset_id: str):
    from pathlib import Path
    from urllib.parse import quote

    from database.enums import AssetModality
    from paths import RAW_AUDIO_DIR, RAW_PDF_DIR, RAW_VIDEO_DIR

    asset_uuid = parse_asset_id(asset_id)

    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_uuid)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    modality_dirs = {
        AssetModality.PDF: RAW_PDF_DIR,
        AssetModality.VIDEO: RAW_VIDEO_DIR,
        AssetModality.AUDIO: RAW_AUDIO_DIR,
    }
    raw_root = PROJECT_ROOT / "storage" / "assets" / "raw"

    raw = Path(asset.raw_path)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(PROJECT_ROOT / raw)
        # Strip storage/assets/raw/ prefix if present
        as_posix = raw.as_posix()
        for prefix in ("storage/assets/raw/", "storage/assets/raw"):
            if as_posix.startswith(prefix):
                candidates.append(raw_root / as_posix[len(prefix) :].lstrip("/"))
                break
        # Bare filename → modality folder
        candidates.append(modality_dirs[asset.modality] / raw.name)
        if asset.name:
            candidates.append(modality_dirs[asset.modality] / Path(asset.name).name)

    file_path: Path | None = next((p for p in candidates if p.is_file()), None)
    if file_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Raw media file not found for asset (raw_path={asset.raw_path!r})",
        )

    try:
        rel = file_path.resolve().relative_to(raw_root.resolve()).as_posix()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Raw file outside storage/assets/raw") from exc

    encoded = "/".join(quote(part) for part in rel.split("/") if part)
    raw_web_path = f"/raw/assets/{encoded}"
    return {
        "asset_id": asset_id,
        "raw_path": raw_web_path,
        "type": asset.modality.value,
    }
