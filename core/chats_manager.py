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
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.chats.config import load_chat_config
from core.chats.llm import stream_chat_completion
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

_STEP_STATUS: dict[str, ChatStatus] = {
    "prepare": ChatStatus.PREPARING,
    "research_search": ChatStatus.RESEARCHING,
    "apply_refetch": ChatStatus.RESEARCHING,
    "research_evaluate": ChatStatus.EVALUATING,
    "expand_media": ChatStatus.STRENGTHENING,
    "infer": ChatStatus.STRENGTHENING,
    "synthesize": ChatStatus.FINALIZING,
}


class ChatEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            dead: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in self._subscribers.get(session_id, []):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(queue)
            for queue in dead:
                self._subscribers[session_id].remove(queue)

    def subscribe(self, session_id: str, *, maxsize: int = 512) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(session_id, [])
        if queue in subs:
            subs.remove(queue)


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
        self.turn_db: AsyncSession | None = None
        self._turn_session_id: uuid.UUID | None = None
        self._turn_seq: int = 0
        self._assistant_message_id: uuid.UUID | None = None
        self._initialized = True

    @property
    def event_bus(self) -> ChatEventBus:
        return self._event_bus

    def _external_id(self) -> str:
        return f"CH-{uuid.uuid4().hex[:8].upper()}"

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

            events = await event_repo.list_recent(session_id, limit=30)
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
        self._assistant_message_id = None
        try:
            async with get_session() as db:
                self.turn_db = db
                self._turn_session_id = session_id
                self._turn_seq = turn_seq

                message_repo = ChatMessageRepo(db)
                messages = await message_repo.list_by_session(session_id)
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
                    await self._emit(
                        session_id,
                        ChatTurnEventType.ERROR,
                        turn_seq,
                        detail={"message": str(result["error"])},
                    )
                    await ChatSessionRepo(db).update_status(session_id, ChatStatus.FAILED)
                    await self._publish_bus("error", {"message": str(result["error"])})
                    return

                answer = result.get("answer") or ""
                assistant_id = result.get("assistant_message_id") or self._assistant_message_id
                if assistant_id and answer:
                    await ChatMessageRepo(db).update_content(uuid.UUID(str(assistant_id)), answer)

                await ChatSessionRepo(db).update_status(session_id, ChatStatus.IDLE)
                await ChatSessionRepo(db).update_retry_count(
                    session_id, int(result.get("retry_index") or 0)
                )
                await self._emit(
                    session_id,
                    ChatTurnEventType.COMPLETED,
                    turn_seq,
                    message_id=uuid.UUID(str(assistant_id)) if assistant_id else None,
                    detail={"answer_length": len(answer)},
                )
                await self._publish_bus(
                    "completed",
                    {
                        "session_id": str(session_id),
                        "turn_seq": turn_seq,
                        "message_id": str(assistant_id) if assistant_id else None,
                    },
                )
        except Exception as exc:
            logger.exception("Chat turn failed for %s", session_id)
            async with get_session() as db:
                await ChatSessionRepo(db).update_status(session_id, ChatStatus.FAILED)
            await self._emit(
                session_id,
                ChatTurnEventType.ERROR,
                turn_seq,
                detail={"message": str(exc)},
            )
            await self._publish_bus("error", {"message": str(exc)})
        finally:
            self.turn_db = None
            self._turn_session_id = None
            self._assistant_message_id = None
            self._active_turns.discard(session_id)

    def _build_conversation_context(self, messages: list[ChatMessageRead], user_message: str) -> str:
        cfg = load_chat_config()
        window = int(cfg.get("context_window_messages", 6))
        recent = messages[-window:] if window > 0 else messages
        lines = [f"{item.role.value}: {item.content}" for item in recent if item.content]
        if not lines or lines[-1] != f"user: {user_message}":
            lines.append(f"user: {user_message}")
        return "\n".join(lines)

    async def on_step_start(self, step: str) -> None:
        if self._turn_session_id is None:
            return
        to_status = _STEP_STATUS.get(step)
        if to_status and self.turn_db is not None:
            session_repo = ChatSessionRepo(self.turn_db)
            current = await session_repo.get_by_id(self._turn_session_id)
            from_status = current.status if current else None
            await session_repo.update_status(self._turn_session_id, to_status)
            await self._emit(
                self._turn_session_id,
                ChatTurnEventType.STEP_START,
                self._turn_seq,
                step_name=step,
                from_status=from_status,
                to_status=to_status,
            )
            await self._publish_bus(
                "step_start",
                {
                    "session_id": str(self._turn_session_id),
                    "turn_seq": self._turn_seq,
                    "step": step,
                    "status": to_status.value,
                },
            )
            await self._publish_bus("state_change", {"status": to_status.value})

    async def emit_evaluation(self, report: Any) -> None:
        if self._turn_session_id is None:
            return
        payload = report.to_dict()
        await self._emit(
            self._turn_session_id,
            ChatTurnEventType.EVALUATION,
            self._turn_seq,
            step_name="research_evaluate",
            detail=payload,
        )
        await self._publish_bus("evaluation", payload)

    async def emit_refetch(self, hint: Any) -> None:
        if self._turn_session_id is None:
            return
        detail = hint if isinstance(hint, dict) else (hint.to_dict() if hint else {})
        await self._emit(
            self._turn_session_id,
            ChatTurnEventType.REFETCH,
            self._turn_seq,
            step_name="apply_refetch",
            detail={"refetch_hint": detail},
        )
        await self._publish_bus("refetch", {"refetch_hint": detail})

    async def emit_research_debug(self, debug: dict[str, Any]) -> None:
        if self._turn_session_id is None:
            return
        await self._emit(
            self._turn_session_id,
            ChatTurnEventType.STEP_COMPLETE,
            self._turn_seq,
            step_name="research_search",
            detail={"debug": debug},
        )

    async def emit_infer_results(self, results: list[dict[str, Any]]) -> None:
        if self._turn_session_id is None:
            return
        await self._emit(
            self._turn_session_id,
            ChatTurnEventType.INFER_RESULT,
            self._turn_seq,
            step_name="infer",
            detail={"results": results},
        )
        for item in results:
            await self._publish_bus(
                "infer_result",
                {"kind": item.get("kind"), "summary": str(item.get("content") or "")[:500]},
            )

    async def ensure_assistant_placeholder(self) -> str:
        if self._assistant_message_id is not None:
            return str(self._assistant_message_id)
        assert self.turn_db is not None and self._turn_session_id is not None
        msg = await ChatMessageRepo(self.turn_db).append_assistant(self._turn_session_id, "")
        self._assistant_message_id = msg.id
        return str(msg.id)

    async def persist_evidence(
        self,
        evidence: list[dict[str, Any]],
        *,
        assistant_message_id: str,
    ) -> None:
        if self.turn_db is None or self._turn_session_id is None:
            return
        await ChatEvidenceRepo(self.turn_db).replace_for_turn(
            self._turn_session_id,
            uuid.UUID(assistant_message_id),
            evidence,
        )
        top_items = evidence[:8]
        await self._emit(
            self._turn_session_id,
            ChatTurnEventType.EVIDENCE_SNAPSHOT,
            self._turn_seq,
            message_id=uuid.UUID(assistant_message_id),
            step_name="expand_media",
            detail={"count": len(evidence), "top_items": top_items},
        )
        await self._publish_bus(
            "evidence_snapshot",
            {"count": len(evidence), "top_items": top_items},
        )

    async def stream_synthesize(self, state: ChatTurnState) -> str:
        prompt = build_synthesize_prompt(state)
        parts: list[str] = []
        async for token in stream_chat_completion(prompt):
            parts.append(token)
            if self._turn_session_id is not None:
                await self._emit(
                    self._turn_session_id,
                    ChatTurnEventType.TOKEN,
                    self._turn_seq,
                    step_name="synthesize",
                    detail={"content": token},
                )
                await self._publish_bus("token", {"content": token})
        return "".join(parts)

    async def _emit(
        self,
        session_id: uuid.UUID,
        event_type: ChatTurnEventType,
        turn_seq: int,
        *,
        message_id: uuid.UUID | None = None,
        step_name: str | None = None,
        from_status: ChatStatus | None = None,
        to_status: ChatStatus | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self.turn_db is not None:
            await ChatTurnEventRepo(self.turn_db).append(
                session_id,
                event_type,
                turn_seq,
                message_id=message_id,
                step_name=step_name,
                from_status=from_status,
                to_status=to_status,
                detail=detail or {},
            )

    async def _publish_bus(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._turn_session_id is None:
            return
        await self._event_bus.publish(
            str(self._turn_session_id),
            {"type": event_type, **payload},
        )


def get_chats_manager() -> ChatsManager:
    return ChatsManager()
