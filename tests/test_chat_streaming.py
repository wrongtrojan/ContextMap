"""Unit tests for chat SSE streaming, token batching, and turn context isolation."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from core.chats.streaming import ChatEventBus, TokenStreamPublisher, stream_next_event
from core.chats.turn_context import TurnContext, get_turn_context, reset_turn_context, set_turn_context
from core.chats_manager import ChatsManager, get_chats_manager
from database.enums import ChatStatus, ChatTurnEventType
from database.repositories import ChatSessionRepo, ChatTurnEventRepo
from database.session import dispose_engine, get_session
from tests.test_chats_e2e import (
    _chat_e2e_patches,
    _sync_chat_manager_singleton,
    _wait_for_idle,
)


@pytest.fixture(autouse=True)
async def reset_manager():
    ChatsManager._instance = None
    _sync_chat_manager_singleton()
    yield
    manager = get_chats_manager()
    for task in list(manager._turn_tasks.values()):
        task.cancel()
    manager._turn_tasks.clear()
    manager._active_turns.clear()
    ChatsManager._instance = None
    await dispose_engine()


@pytest.mark.asyncio
async def test_event_bus_milestone_survives_token_flood():
    bus = ChatEventBus()
    session_id = str(uuid.uuid4())
    sub = await bus.subscribe(session_id)

    for _ in range(1500):
        await bus.publish(session_id, {"type": "token", "content": "t"})
    await bus.publish(session_id, {"type": "completed", "turn_seq": 1})

    seen: list[str] = []
    deadline = asyncio.get_event_loop().time() + 5.0
    while asyncio.get_event_loop().time() < deadline:
        try:
            event = await stream_next_event(sub, timeout=0.5, batch_ms=10, batch_chars=64)
        except asyncio.TimeoutError:
            continue
        seen.append(str(event.get("type")))
        if event.get("type") == "completed":
            break
    else:
        pytest.fail(f"Timed out waiting for completed; saw {seen[-10:]}")

    assert "completed" in seen


@pytest.mark.asyncio
async def test_token_stream_publisher_batches():
    bus = ChatEventBus()
    session_id = str(uuid.uuid4())
    sub = await bus.subscribe(session_id)
    publisher = TokenStreamPublisher(bus, session_id, batch_ms=1000, batch_chars=100)

    for _ in range(30):
        await publisher.append("abc")
    await publisher.flush()
    await bus.flush_token_buffers(session_id, force=True)

    event = await stream_next_event(sub, timeout=2.0, batch_ms=10, batch_chars=64)
    assert event["type"] == "token"
    assert len(event["content"]) >= 90


@pytest.mark.asyncio
async def test_turn_context_isolated_between_tasks():
    results: dict[str, uuid.UUID | None] = {}

    async def worker(name: str, session_id: uuid.UUID) -> None:
        token = set_turn_context(TurnContext(session_id=session_id, turn_seq=1))
        await asyncio.sleep(0.05)
        ctx = get_turn_context()
        results[name] = ctx.session_id if ctx else None
        reset_turn_context(token)

    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    await asyncio.gather(worker("a", id_a), worker("b", id_b))
    assert results["a"] == id_a
    assert results["b"] == id_b


@pytest.mark.asyncio
async def test_mock_turn_persists_no_token_events():
    async with _chat_e2e_patches():
        manager = get_chats_manager()
        session = await manager.create_session()
        try:
            await manager.start_turn(session.id, "Explain paging")
            detail = await _wait_for_idle(str(session.id))
            event_types = {item["type"] for item in detail["events"]}
            assert ChatTurnEventType.TOKEN.value not in event_types
            assert ChatTurnEventType.COMPLETED.value in event_types
        finally:
            async with get_session() as db:
                await ChatSessionRepo(db).delete(session.id)


@pytest.mark.asyncio
async def test_poll_sees_non_idle_status_mid_turn():
    gate = asyncio.Event()

    async def _slow_synthesize(_state, _manager):
        await gate.wait()
        return {"answer": "done mid-turn"}

    async with _chat_e2e_patches():
        manager = get_chats_manager()
        session = await manager.create_session()
        try:
            with patch("core.chats_graph.node_synthesize", new=AsyncMock(side_effect=_slow_synthesize)):
                await manager.start_turn(session.id, "hold synthesize")
                saw_busy = False
                for _ in range(40):
                    detail = await manager.get_session_detail(session.id)
                    assert detail is not None
                    if detail["status"] != ChatStatus.IDLE.value:
                        saw_busy = True
                        break
                    await asyncio.sleep(0.05)
                gate.set()
                await _wait_for_idle(str(session.id))
            assert saw_busy, "poll should observe in-progress status before turn completes"
        finally:
            async with get_session() as db:
                await ChatSessionRepo(db).delete(session.id)


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_cross_events():
    async with _chat_e2e_patches():
        manager = get_chats_manager()
        session_a = await manager.create_session(chat_name="A")
        session_b = await manager.create_session(chat_name="B")
        try:
            await asyncio.gather(
                manager.start_turn(session_a.id, "question A"),
                manager.start_turn(session_b.id, "question B"),
            )
            detail_a = await _wait_for_idle(str(session_a.id), timeout=25.0)
            detail_b = await _wait_for_idle(str(session_b.id), timeout=25.0)

            async with get_session() as db:
                events_a = await ChatTurnEventRepo(db).list_milestones(session_a.id, limit=50)
                events_b = await ChatTurnEventRepo(db).list_milestones(session_b.id, limit=50)

            assert all(item.session_id == session_a.id for item in events_a)
            assert all(item.session_id == session_b.id for item in events_b)
            assert detail_a["messages"][0]["content"] == "question A"
            assert detail_b["messages"][0]["content"] == "question B"
        finally:
            async with get_session() as db:
                await ChatSessionRepo(db).delete(session_a.id)
                await ChatSessionRepo(db).delete(session_b.id)
