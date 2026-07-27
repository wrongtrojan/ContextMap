"""Tests for services.cleanup.sessions."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from database.enums import MessageRole
from database.repositories import ChatMessageRepo, ChatSessionRepo
from database.schemas import ChatSessionCreate
from database.session import get_session
from services.cleanup.session_delete_queue import SessionDeleteQueue
from services.cleanup.sessions import cleanup_all_sessions, delete_session_record


@pytest.mark.asyncio
async def test_delete_empty_session() -> None:
    async with get_session() as session:
        created = await ChatSessionRepo(session).create(
            ChatSessionCreate(chat_name="delete-me", external_id="DEL-TEST01")
        )
        session_id = created.id

    deleted = await delete_session_record(session_id)
    assert deleted is True

    async with get_session() as session:
        assert await ChatSessionRepo(session).get_by_id(session_id) is None


@pytest.mark.asyncio
async def test_delete_session_with_messages_uses_sql_cascade() -> None:
    async with get_session() as session:
        created = await ChatSessionRepo(session).create(
            ChatSessionCreate(chat_name="cascade-me", external_id=f"DEL-{uuid.uuid4().hex[:8].upper()}")
        )
        session_id = created.id
        await ChatMessageRepo(session).append_user(session_id, "hello")
        await ChatMessageRepo(session).append_assistant(session_id, "world")

    t0 = time.perf_counter()
    deleted = await delete_session_record(session_id, force=True)
    elapsed = time.perf_counter() - t0
    assert deleted is True
    assert elapsed < 1.0

    async with get_session() as session:
        assert await ChatSessionRepo(session).get_by_id(session_id) is None
        assert await ChatMessageRepo(session).list_by_session(session_id) == []


@pytest.mark.asyncio
async def test_delete_queue_accepts_immediately_and_drains() -> None:
    async with get_session() as session:
        created = await ChatSessionRepo(session).create(
            ChatSessionCreate(chat_name="queue-me", external_id=f"DEL-{uuid.uuid4().hex[:8].upper()}")
        )
        session_id = created.id

    q = SessionDeleteQueue()
    await q.start()
    try:
        assert q.enqueue(session_id) is True
        assert q.enqueue(session_id) is False  # dedupe
        await asyncio.wait_for(q._queue.join(), timeout=3.0)
    finally:
        await q.stop()

    async with get_session() as session:
        assert await ChatSessionRepo(session).get_by_id(session_id) is None


@pytest.mark.asyncio
async def test_cleanup_sessions_dry_run() -> None:
    report = await cleanup_all_sessions(dry_run=True)
    assert report.scanned >= 0
