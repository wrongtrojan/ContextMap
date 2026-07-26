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
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset_id UUID") from exc
    await get_assets_manager().retry(asset_uuid)
    return {"status": "success", "message": "Asset re-enqueued", "asset_id": asset_id}


@router.get("/stream")
async def asset_stream(request: Request, asset_id: str = Query(...)):
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset_id UUID") from exc

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
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset_id UUID") from exc

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


@router.get("/preview")
async def get_preview(asset_id: str):
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset_id UUID") from exc

    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_uuid)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    raw_web_path = asset.raw_path.replace("storage/assets/raw", "/raw/assets")
    return {
        "asset_id": asset_id,
        "raw_path": raw_web_path,
        "type": asset.modality.value,
    }
