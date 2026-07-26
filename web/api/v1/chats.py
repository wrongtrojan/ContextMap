import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.chats_manager import get_chats_manager

router = APIRouter()
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
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID") from exc

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


@router.get("/stream")
async def chat_stream(request: Request, session_id: str = Query(...)):
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID") from exc

    manager = get_chats_manager()
    queue = manager.event_bus.subscribe(session_id)

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
            manager.event_bus.unsubscribe(session_id, queue)

    return EventSourceResponse(event_generator())
