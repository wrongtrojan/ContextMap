import uuid

from fastapi import APIRouter, HTTPException, Query

from core.assets_manager import get_assets_manager
from core.chats_manager import get_chats_manager
from database.repositories import AssetRepo, PipelineEventRepo
from database.session import get_session
from web.api.deps import parse_asset_id, parse_session_id

router = APIRouter()
chats_manager = get_chats_manager()


def _event_to_dict(event) -> dict:
    return {
        "type": event.event_type.value,
        "step": event.step_name,
        "from_status": event.from_status.value if event.from_status else None,
        "to_status": event.to_status.value if event.to_status else None,
        "detail": event.detail,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


async def _asset_status_payload(asset_id: uuid.UUID) -> dict:
    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        events = await PipelineEventRepo(session).list_recent(asset_id, limit=20)
    latest_step = events[0].step_name if events else None
    return {
        "asset_id": str(asset.id),
        "name": asset.name,
        "modality": asset.modality.value,
        "status": asset.status.value,
        "kg_status": asset.kg_status.value,
        "triple_count": asset.triple_count,
        "raw_path": asset.raw_path,
        "processed_path": asset.processed_path,
        "error_message": asset.error_message,
        "retry_count": asset.retry_count,
        "current_step": latest_step,
        "events": [_event_to_dict(item) for item in reversed(events)],
    }


@router.get("/single_asset")
async def get_single_status(asset_id: str | None = Query(None)):
    if asset_id:
        asset_uuid = parse_asset_id(asset_id)
        return {"status": "success", "data": await _asset_status_payload(asset_uuid)}

    async with get_session() as session:
        assets = await AssetRepo(session).list_all()
    return {
        "status": "success",
        "data": {
            str(item.id): {
                "asset_id": str(item.id),
                "name": item.name,
                "modality": item.modality.value,
                "status": item.status.value,
                "kg_status": item.kg_status.value,
                "triple_count": item.triple_count,
                "raw_path": item.raw_path,
                "processed_path": item.processed_path,
                "error_message": item.error_message,
            }
            for item in assets
        },
    }


@router.get("/global_assets")
async def get_global_status():
    manager = get_assets_manager()
    async with get_session() as session:
        assets = await AssetRepo(session).list_all()
    active = len(manager._active)
    return {
        "status": "success",
        "data": {
            "assets_number": len(assets),
            "active_pipelines": active,
            "queue_length": manager._queue.qsize(),
        },
    }


@router.get("/single_chat")
async def get_single_chat_status(session_id: str | None = Query(None)):
    if session_id:
        session_uuid = parse_session_id(session_id)
        detail = await chats_manager.get_session_detail(session_uuid)
        if detail is None:
            return {"status": "error", "message": "Not Found"}
        return {"status": "success", "data": detail}

    sessions = await chats_manager.list_sessions()
    return {
        "status": "success",
        "data": {item["session_id"]: item for item in sessions},
    }


@router.get("/global_chats")
async def get_global_chat_status():
    sessions = await chats_manager.list_sessions()
    global_meta = chats_manager.get_global_status()
    querying = any(item["status"] != "idle" for item in sessions)
    return {
        "status": "success",
        "data": {
            "chats_number": len(sessions),
            "chats_status": "querying" if querying else "waiting",
            "active_turns": global_meta["active_turns"],
        },
    }
