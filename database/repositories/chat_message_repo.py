from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import MessageRole
from database.models import ChatMessage
from database.schemas import ChatMessageRead


class ChatMessageRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _next_seq(self, session_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(ChatMessage.seq), 0)).where(ChatMessage.session_id == session_id)
        result = await self.session.execute(stmt)
        current = int(result.scalar_one())
        return current + 1

    async def append(
        self,
        session_id: uuid.UUID,
        *,
        role: MessageRole,
        content: str,
    ) -> ChatMessageRead:
        row = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            seq=await self._next_seq(session_id),
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return ChatMessageRead.model_validate(row)

    async def append_user(self, session_id: uuid.UUID, content: str) -> ChatMessageRead:
        return await self.append(session_id, role=MessageRole.USER, content=content)

    async def append_assistant(self, session_id: uuid.UUID, content: str) -> ChatMessageRead:
        return await self.append(session_id, role=MessageRole.ASSISTANT, content=content)

    async def list_by_session(self, session_id: uuid.UUID) -> list[ChatMessageRead]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.asc())
        )
        result = await self.session.execute(stmt)
        return [ChatMessageRead.model_validate(item) for item in result.scalars().all()]

    async def count_turns(self, session_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == MessageRole.USER,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def update_content(self, message_id: uuid.UUID, content: str) -> ChatMessageRead | None:
        row = await self.session.get(ChatMessage, message_id)
        if row is None:
            return None
        row.content = content
        await self.session.flush()
        await self.session.refresh(row)
        return ChatMessageRead.model_validate(row)
