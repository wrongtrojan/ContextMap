"""
Chat session orchestration: LangGraph turn pipeline + PostgreSQL + SSE event bus.

Usage:
  manager = get_chats_manager()
  session = await manager.create_session()
  turn_seq = await manager.start_turn(session.id, "user question")
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from core.chats.config import load_chat_config
from core.chats.llm import stream_chat_completion
from core.chats.streaming import ChatEventBus, TokenStreamPublisher
from core.chats.turn_context import (
    TurnContext,
    get_turn_context,
    require_turn_context,
    reset_turn_context,
    set_turn_context,
)
from core.chats_graph import ChatTurnState, build_chat_graph, build_synthesize_prompt
from database.enums import ChatStatus, ChatTurnEventType, MessageRole
from database.repositories import (
    ChatEvidenceRepo,
    ChatMessageRepo,
    ChatSessionRepo,
    ChatTurnEventRepo,
)
from database.schemas import ChatMessageRead, ChatSessionCreate, ChatSessionRead
from database.session import get_session

logger = logging.getLogger("ChatsManager")

T = TypeVar("T")

_STEP_STATUS: dict[str, ChatStatus] = {
    "prepare": ChatStatus.PREPARING,
    "research_search": ChatStatus.RESEARCHING,
    "apply_refetch": ChatStatus.RESEARCHING,
    "research_evaluate": ChatStatus.EVALUATING,
    "expand_media": ChatStatus.STRENGTHENING,
    "infer": ChatStatus.STRENGTHENING,
    "synthesize": ChatStatus.FINALIZING,
}


class ChatsManager:
    _instance: ChatsManager | None = None

    def __new__(cls) -> ChatsManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._event_bus = ChatEventBus()
        self._active_turns: set[uuid.UUID] = set()
        self._turn_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._initialized = True

    @property
    def event_bus(self) -> ChatEventBus:
        return self._event_bus

    def _external_id(self) -> str:
        return f"CH-{uuid.uuid4().hex[:8].upper()}"

    def _milestone_limit(self) -> int:
        cfg = load_chat_config()
        return int((cfg.get("events") or {}).get("milestone_limit", 30))

    def _streaming_cfg(self) -> dict[str, Any]:
        return dict(load_chat_config().get("streaming") or {})

    def _sse_batch_kwargs(self, streaming: dict[str, Any] | None = None) -> dict[str, float | int]:
        cfg = streaming or self._streaming_cfg()
        return {
            "batch_ms": float(cfg.get("sse_token_batch_ms", 50)),
            "batch_chars": int(cfg.get("sse_token_batch_chars", 256)),
        }

    async def _flush_sse_tokens(
        self,
        session_id: str | uuid.UUID,
        *,
        force: bool = True,
        streaming: dict[str, Any] | None = None,
    ) -> None:
        await self._event_bus.flush_token_buffers(
            str(session_id),
            force=force,
            **self._sse_batch_kwargs(streaming),
        )

    async def _commit(
        self,
        fn: Callable[[AsyncSession], Awaitable[T]],
    ) -> T:
        async with get_session() as session:
            return await fn(session)

    async def create_session(self, *, chat_name: str = "New Academic Chat") -> ChatSessionRead:
        async with get_session() as session:
            repo = ChatSessionRepo(session)
            return await repo.create(
                ChatSessionCreate(external_id=self._external_id(), chat_name=chat_name)
            )

    async def get_session_detail(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        async with get_session() as session:
            session_repo = ChatSessionRepo(session)
            message_repo = ChatMessageRepo(session)
            evidence_repo = ChatEvidenceRepo(session)
            event_repo = ChatTurnEventRepo(session)

            chat_session = await session_repo.get_by_id(session_id)
            if chat_session is None:
                return None

            limit = self._milestone_limit()
            events = await event_repo.list_milestones(session_id, limit=limit)
            latest_step = events[0].step_name if events else None

            return {
                "session_id": str(chat_session.id),
                "external_id": chat_session.external_id,
                "chat_name": chat_session.chat_name,
                "status": chat_session.status.value,
                "retry_count": chat_session.retry_count,
                "current_step": latest_step,
                "messages": [
                    {
                        "id": str(item.id),
                        "role": item.role.value,
                        "content": item.content,
                        "seq": item.seq,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in await message_repo.list_by_session(session_id)
                ],
                "evidences": [
                    {
                        "id": str(item.id),
                        "message_id": str(item.message_id) if item.message_id else None,
                        "content_unit_id": str(item.content_unit_id) if item.content_unit_id else None,
                        "content": item.content,
                        "score": item.score,
                        "rank": item.rank,
                        "source": item.source,
                        "metadata": item.metadata,
                    }
                    for item in await evidence_repo.list_by_session(session_id)
                ],
                "events": [
                    {
                        "type": item.event_type.value,
                        "step": item.step_name,
                        "turn_seq": item.turn_seq,
                        "from_status": item.from_status.value if item.from_status else None,
                        "to_status": item.to_status.value if item.to_status else None,
                        "detail": item.detail,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in reversed(events)
                ],
            }

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            repo = ChatSessionRepo(session)
            rows = await repo.list_all()
            return [
                {
                    "session_id": str(item.id),
                    "external_id": item.external_id,
                    "chat_name": item.chat_name,
                    "status": item.status.value,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in rows
            ]

    def get_global_status(self) -> dict[str, Any]:
        return {
            "active_turns": len(self._active_turns),
            "running_tasks": len(self._turn_tasks),
        }

    async def cancel_turn(self, session_id: uuid.UUID) -> None:
        """Cancel an in-flight turn so the session can be deleted."""
        self.request_cancel_turn(session_id)
        task = self._turn_tasks.get(session_id)
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._turn_tasks.pop(session_id, None)
        self._active_turns.discard(session_id)
        try:
            await asyncio.wait_for(self._flush_sse_tokens(session_id, force=True), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning("Timed out flushing SSE tokens for session %s", session_id)
        try:
            await asyncio.wait_for(
                self._event_bus.publish(
                    str(session_id),
                    {"type": "error", "message": "Turn cancelled"},
                ),
                timeout=1.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Timed out publishing cancel event for session %s", session_id)

    def request_cancel_turn(self, session_id: uuid.UUID) -> None:
        """Best-effort, non-blocking cancel for fast delete paths."""
        task = self._turn_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
        self._active_turns.discard(session_id)

    async def start_turn(self, session_id: uuid.UUID, user_message: str) -> int:
        if session_id in self._active_turns:
            raise RuntimeError("A turn is already running for this session")

        async with get_session() as session:
            session_repo = ChatSessionRepo(session)
            message_repo = ChatMessageRepo(session)
            chat_session = await session_repo.get_by_id(session_id)
            if chat_session is None:
                raise ValueError(f"Session not found: {session_id}")

            await message_repo.append_user(session_id, user_message)
            turn_seq = await message_repo.count_turns(session_id)

            messages = await message_repo.list_by_session(session_id)
            if len(messages) == 1:
                name = f"Chat-{user_message[:24].strip() or 'New'}"
                await session_repo.update_chat_name(session_id, name)

        self._active_turns.add(session_id)
        task = asyncio.create_task(self._run_turn_graph(session_id, turn_seq, user_message))
        self._turn_tasks[session_id] = task
        task.add_done_callback(lambda _: self._turn_tasks.pop(session_id, None))
        return turn_seq

    async def _run_turn_graph(self, session_id: uuid.UUID, turn_seq: int, user_message: str) -> None:
        ctx = TurnContext(session_id=session_id, turn_seq=turn_seq)
        token = set_turn_context(ctx)
        try:
            async with get_session() as session:
                messages = await ChatMessageRepo(session).list_by_session(session_id)
            conversation_context = self._build_conversation_context(messages, user_message)

            graph = build_chat_graph(self)
            state: ChatTurnState = {
                "session_id": str(session_id),
                "turn_seq": turn_seq,
                "user_query": user_message,
                "conversation_context": conversation_context,
            }
            result = await graph.ainvoke(state)

            if result.get("error"):
                await self._record_error(str(result["error"]))
                return

            answer = result.get("answer") or ""
            assistant_id = result.get("assistant_message_id") or ctx.assistant_message_id
            retry_index = int(result.get("retry_index") or 0)

            async def _finalize(db: AsyncSession) -> None:
                if assistant_id and answer:
                    await ChatMessageRepo(db).update_content(uuid.UUID(str(assistant_id)), answer)
                await ChatSessionRepo(db).update_status(session_id, ChatStatus.IDLE)
                await ChatSessionRepo(db).update_retry_count(session_id, retry_index)
                await ChatTurnEventRepo(db).append(
                    session_id,
                    ChatTurnEventType.COMPLETED,
                    turn_seq,
                    message_id=uuid.UUID(str(assistant_id)) if assistant_id else None,
                    detail={"answer_length": len(answer)},
                )

            await self._commit(_finalize)
            await self._publish_bus(
                "completed",
                {
                    "session_id": str(session_id),
                    "turn_seq": turn_seq,
                    "message_id": str(assistant_id) if assistant_id else None,
                },
            )
            await self._flush_sse_tokens(session_id)
        except Exception as exc:
            logger.exception("Chat turn failed for %s", session_id)
            await self._record_error(str(exc))
        finally:
            reset_turn_context(token)
            self._active_turns.discard(session_id)

    async def _record_error(self, message: str) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return

        async def _fail(db: AsyncSession) -> None:
            await ChatSessionRepo(db).update_status(ctx.session_id, ChatStatus.FAILED)
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.ERROR,
                ctx.turn_seq,
                detail={"message": message},
            )

        await self._commit(_fail)
        await self._publish_bus("error", {"message": message})
        await self._flush_sse_tokens(ctx.session_id)

    def _build_conversation_context(self, messages: list[ChatMessageRead], user_message: str) -> str:
        cfg = load_chat_config()
        window = int(cfg.get("context_window_messages", 6))
        recent = messages[-window:] if window > 0 else messages
        lines = [f"{item.role.value}: {item.content}" for item in recent if item.content]
        if not lines or lines[-1] != f"user: {user_message}":
            lines.append(f"user: {user_message}")
        return "\n".join(lines)

    async def on_step_start(self, step: str) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return
        to_status = _STEP_STATUS.get(step)
        if to_status is None:
            return

        async def _start(db: AsyncSession) -> ChatStatus | None:
            session_repo = ChatSessionRepo(db)
            current = await session_repo.get_by_id(ctx.session_id)
            from_status = current.status if current else None
            await session_repo.update_status(ctx.session_id, to_status)
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.STEP_START,
                ctx.turn_seq,
                step_name=step,
                from_status=from_status,
                to_status=to_status,
            )
            return from_status

        await self._commit(_start)
        await self._publish_bus(
            "step_start",
            {
                "session_id": str(ctx.session_id),
                "turn_seq": ctx.turn_seq,
                "step": step,
                "status": to_status.value,
            },
        )
        await self._publish_bus("state_change", {"status": to_status.value})

    async def emit_evaluation(self, report: Any) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return
        payload = report.to_dict()

        async def _eval(db: AsyncSession) -> None:
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.EVALUATION,
                ctx.turn_seq,
                step_name="research_evaluate",
                detail=payload,
            )

        await self._commit(_eval)
        await self._publish_bus("evaluation", payload)

    async def emit_refetch(self, hint: Any) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return
        detail = hint if isinstance(hint, dict) else (hint.to_dict() if hint else {})

        async def _refetch(db: AsyncSession) -> None:
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.REFETCH,
                ctx.turn_seq,
                step_name="apply_refetch",
                detail={"refetch_hint": detail},
            )

        await self._commit(_refetch)
        await self._publish_bus("refetch", {"refetch_hint": detail})

    async def emit_research_debug(self, debug: dict[str, Any]) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return

        async def _debug(db: AsyncSession) -> None:
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.STEP_COMPLETE,
                ctx.turn_seq,
                step_name="research_search",
                detail={"debug": debug},
            )

        await self._commit(_debug)

    async def emit_infer_results(self, results: list[dict[str, Any]]) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return

        async def _infer(db: AsyncSession) -> None:
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.INFER_RESULT,
                ctx.turn_seq,
                step_name="infer",
                detail={"results": results},
            )

        await self._commit(_infer)
        for item in results:
            await self._publish_bus(
                "infer_result",
                {"kind": item.get("kind"), "summary": str(item.get("content") or "")[:500]},
            )

    async def ensure_assistant_placeholder(self) -> str:
        ctx = require_turn_context()
        if ctx.assistant_message_id is not None:
            return str(ctx.assistant_message_id)

        async def _placeholder(db: AsyncSession) -> uuid.UUID:
            msg = await ChatMessageRepo(db).append_assistant(ctx.session_id, "")
            return msg.id

        msg_id = await self._commit(_placeholder)
        ctx.assistant_message_id = msg_id
        return str(msg_id)

    async def persist_evidence(
        self,
        evidence: list[dict[str, Any]],
        *,
        assistant_message_id: str,
    ) -> None:
        ctx = require_turn_context()
        top_items = evidence[:8]

        async def _persist(db: AsyncSession) -> None:
            await ChatEvidenceRepo(db).replace_for_turn(
                ctx.session_id,
                uuid.UUID(assistant_message_id),
                evidence,
            )
            await ChatTurnEventRepo(db).append(
                ctx.session_id,
                ChatTurnEventType.EVIDENCE_SNAPSHOT,
                ctx.turn_seq,
                message_id=uuid.UUID(assistant_message_id),
                step_name="expand_media",
                detail={"count": len(evidence), "top_items": top_items},
            )

        await self._commit(_persist)
        await self._publish_bus(
            "evidence_snapshot",
            {"count": len(evidence), "top_items": top_items},
        )

    async def stream_synthesize(self, state: ChatTurnState) -> str:
        ctx = require_turn_context()
        cfg = load_chat_config()
        streaming = self._streaming_cfg()
        events_cfg = cfg.get("events") or {}
        persist_tokens = bool(events_cfg.get("persist_tokens", False))

        publisher = TokenStreamPublisher(
            self._event_bus,
            str(ctx.session_id),
            batch_ms=float(streaming.get("sse_token_batch_ms", 50)),
            batch_chars=int(streaming.get("sse_token_batch_chars", 256)),
        )
        flush_chars = int(streaming.get("assistant_flush_chars", 512))
        flush_sec = float(streaming.get("assistant_flush_sec", 2.0))

        prompt = build_synthesize_prompt(state)
        parts: list[str] = []
        since_flush = time.monotonic()
        chars_since_flush = 0

        async for token in stream_chat_completion(prompt):
            parts.append(token)
            await publisher.append(token)
            chars_since_flush += len(token)
            elapsed = time.monotonic() - since_flush

            if persist_tokens:
                async def _token_event(db: AsyncSession) -> None:
                    await ChatTurnEventRepo(db).append(
                        ctx.session_id,
                        ChatTurnEventType.TOKEN,
                        ctx.turn_seq,
                        step_name="synthesize",
                        detail={"content": token},
                    )

                await self._commit(_token_event)

            assistant_id = ctx.assistant_message_id
            if assistant_id and (chars_since_flush >= flush_chars or elapsed >= flush_sec):
                content = "".join(parts)

                async def _flush_msg(db: AsyncSession, content=content, aid=assistant_id) -> None:
                    await ChatMessageRepo(db).update_content(uuid.UUID(str(aid)), content)

                await self._commit(_flush_msg)
                since_flush = time.monotonic()
                chars_since_flush = 0

        await publisher.flush()
        await self._flush_sse_tokens(ctx.session_id, streaming=streaming)
        return "".join(parts)

    async def _publish_bus(self, event_type: str, payload: dict[str, Any]) -> None:
        ctx = get_turn_context()
        if ctx is None:
            return
        await self._event_bus.publish(
            str(ctx.session_id),
            {"type": event_type, **payload},
        )


def get_chats_manager() -> ChatsManager:
    return ChatsManager()
