from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import ChatStatus, ChatTurnEventType
from database.models import ChatTurnEvent
from database.schemas import ChatTurnEventRead


class ChatTurnEventRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
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
    ) -> ChatTurnEventRead:
        event = ChatTurnEvent(
            session_id=session_id,
            message_id=message_id,
            turn_seq=turn_seq,
            event_type=event_type,
            step_name=step_name,
            from_status=from_status,
            to_status=to_status,
            detail=detail or {},
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return ChatTurnEventRead.model_validate(event)

    async def list_recent(
        self,
        session_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[ChatTurnEventRead]:
        stmt = (
            select(ChatTurnEvent)
            .where(ChatTurnEvent.session_id == session_id)
            .order_by(ChatTurnEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [ChatTurnEventRead.model_validate(item) for item in result.scalars().all()]
