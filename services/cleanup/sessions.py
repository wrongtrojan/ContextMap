"""Chat session cleanup.

Strategy:
  - API path enqueues and returns immediately (see session_delete_queue).
  - Actual delete uses one SQL DELETE on chat_sessions; Postgres FK CASCADE
    removes messages / evidences / turn_events. Never ORM relationship cascade.
  - Active turns are cancelled best-effort and non-blocking before the SQL delete.
"""

from __future__ import annotations

import logging
import uuid

from core.chats_manager import get_chats_manager
from database.enums import ChatStatus
from database.repositories import ChatMessageRepo, ChatSessionRepo
from database.schemas import ChatSessionRead
from database.session import get_session
from services.cleanup.types import CleanupReport

logger = logging.getLogger("SessionCleanup")


async def find_empty_sessions() -> list[ChatSessionRead]:
    async with get_session() as session:
        sessions = await ChatSessionRepo(session).list_all()
        result: list[ChatSessionRead] = []
        for s in sessions:
            msgs = await ChatMessageRepo(session).list_by_session(s.id)
            if len(msgs) == 0:
                result.append(s)
    return result


def _release_turn(session_id: uuid.UUID) -> None:
    """Drop in-memory turn state without waiting on SSE / task teardown."""
    try:
        get_chats_manager().request_cancel_turn(session_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to request turn cancel for %s", session_id)


async def delete_session_record(session_id: uuid.UUID, *, force: bool = False) -> bool:
    """Delete one session quickly via SQL CASCADE.

    If a turn is active and force=False, skip. With force=True (API default),
    cancel the turn best-effort then delete.
    """
    manager = get_chats_manager()
    if session_id in manager._active_turns and not force:
        return False

    _release_turn(session_id)

    async with get_session() as session:
        deleted = await ChatSessionRepo(session).delete(session_id)
    return deleted


async def cleanup_all_sessions(*, dry_run: bool = True, only_idle: bool = True) -> CleanupReport:
    report = CleanupReport()
    async with get_session() as session:
        sessions = await ChatSessionRepo(session).list_all()

    targets = [s for s in sessions if not only_idle or s.status == ChatStatus.IDLE]
    report.scanned = len(targets)

    for s in targets:
        if dry_run:
            report.deleted_ids.append(str(s.id))
            continue
        try:
            ok = await delete_session_record(s.id, force=True)
            if ok:
                report.deleted += 1
                report.deleted_ids.append(str(s.id))
            else:
                report.skipped += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"{s.id}: {exc}")
            report.skipped += 1

    if dry_run:
        report.deleted = len(report.deleted_ids)

    return report
