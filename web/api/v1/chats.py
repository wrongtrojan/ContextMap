import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.chats.config import load_chat_config
from core.chats.streaming import stream_next_event
from core.chats_manager import get_chats_manager
from web.api.deps import parse_session_id

router = APIRouter()
logger = logging.getLogger("ChatsAPI")
chats_manager = get_chats_manager()


class TurnRequest(BaseModel):
    message: str = Field(..., min_length=1)


@router.post("/sessions")
async def create_session():
    session = await chats_manager.create_session()
    return {
        "status": "success",
        "session_id": str(session.id),
        "external_id": session.external_id,
        "chat_status": session.status.value,
    }


@router.post("/sessions/{session_id}/turns")
async def start_turn(session_id: str, body: TurnRequest):
    session_uuid = parse_session_id(session_id)

    if session_uuid in chats_manager._active_turns:
        raise HTTPException(status_code=409, detail="Turn already running for this session")

    try:
        turn_seq = await chats_manager.start_turn(session_uuid, body.message.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "status": "success",
        "session_id": session_id,
        "turn_seq": turn_seq,
        "message": "Turn started",
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, force: bool = Query(True)):
    """Enqueue session delete and return immediately.

    Actual removal (SQL CASCADE) runs on a serial background worker so the
    UI can keep deleting without waiting on DB / active turns.
    """
    from services.cleanup.session_delete_queue import get_session_delete_queue

    session_uuid = parse_session_id(session_id)
    queued = get_session_delete_queue().enqueue(session_uuid)
    if not force:
        logger.debug("Delete queued with force=false for %s; treated as force", session_id)
    return {
        "status": "accepted",
        "session_id": session_id,
        "queued": queued,
        "pending": get_session_delete_queue().pending_count,
    }


@router.get("/stream")
async def chat_stream(request: Request, session_id: str = Query(...)):
    session_uuid = parse_session_id(session_id)

    manager = get_chats_manager()
    streaming = load_chat_config().get("streaming") or {}
    batch_ms = float(streaming.get("sse_token_batch_ms", 50))
    batch_chars = int(streaming.get("sse_token_batch_chars", 256))
    sub = await manager.event_bus.subscribe(session_id)

    async def event_generator():
        try:
            detail = await manager.get_session_detail(session_uuid)
            if detail is None:
                yield {"event": "error", "data": json.dumps({"message": "Session not found"})}
                return
            yield {
                "event": "state_change",
                "data": json.dumps({"status": detail["status"]}, ensure_ascii=False),
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await stream_next_event(
                        sub,
                        timeout=15.0,
                        batch_ms=batch_ms,
                        batch_chars=batch_chars,
                    )
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
            await manager.event_bus.unsubscribe(session_id, sub)

    return EventSourceResponse(event_generator())
