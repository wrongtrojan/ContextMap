"""Serial background queue for chat session deletes.

API returns immediately after enqueue. A single worker drains the queue so
Postgres never sees concurrent CASCADE deletes fighting over the same rows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger("SessionDeleteQueue")


class SessionDeleteQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._pending: set[uuid.UUID] = set()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def enqueue(self, session_id: uuid.UUID) -> bool:
        """Queue a delete. Returns False if already pending (deduped)."""
        if session_id in self._pending:
            return False
        self._pending.add(session_id)
        self._queue.put_nowait(session_id)
        return True

    def enqueue_many(self, session_ids: list[uuid.UUID]) -> int:
        return sum(1 for sid in session_ids if self.enqueue(sid))

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="session-delete-queue")
        logger.info("Session delete queue started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("Session delete queue stopped")

    async def _worker_loop(self) -> None:
        from services.cleanup.sessions import delete_session_record

        while self._running:
            session_id = await self._queue.get()
            try:
                await delete_session_record(session_id, force=True)
            except Exception:
                logger.exception("Failed to delete session %s", session_id)
            finally:
                self._pending.discard(session_id)
                self._queue.task_done()


_queue: SessionDeleteQueue | None = None


def get_session_delete_queue() -> SessionDeleteQueue:
    global _queue
    if _queue is None:
        _queue = SessionDeleteQueue()
    return _queue
