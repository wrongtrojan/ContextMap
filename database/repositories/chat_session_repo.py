from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import ChatStatus
from database.models import ChatSession
from database.schemas import ChatSessionCreate, ChatSessionRead


class ChatSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ChatSessionCreate, session_id: uuid.UUID | None = None) -> ChatSessionRead:
        row = ChatSession(
            id=session_id or uuid.uuid4(),
            external_id=payload.external_id,
            chat_name=payload.chat_name,
            status=payload.status,
            metadata_=payload.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return ChatSessionRead.model_validate(row)

    async def get_by_id(self, session_id: uuid.UUID) -> ChatSessionRead | None:
        row = await self.session.get(ChatSession, session_id)
        return ChatSessionRead.model_validate(row) if row else None

    async def get_by_external_id(self, external_id: str) -> ChatSessionRead | None:
        stmt = select(ChatSession).where(ChatSession.external_id == external_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return ChatSessionRead.model_validate(row) if row else None

    async def list_all(self) -> list[ChatSessionRead]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
        result = await self.session.execute(stmt)
        return [ChatSessionRead.model_validate(item) for item in result.scalars().all()]

    async def update_status(self, session_id: uuid.UUID, status: ChatStatus) -> ChatSessionRead | None:
        row = await self.session.get(ChatSession, session_id)
        if row is None:
            return None
        row.status = status
        await self.session.flush()
        await self.session.refresh(row)
        return ChatSessionRead.model_validate(row)

    async def update_retry_count(self, session_id: uuid.UUID, retry_count: int) -> ChatSessionRead | None:
        row = await self.session.get(ChatSession, session_id)
        if row is None:
            return None
        row.retry_count = retry_count
        await self.session.flush()
        await self.session.refresh(row)
        return ChatSessionRead.model_validate(row)

    async def update_chat_name(self, session_id: uuid.UUID, chat_name: str) -> ChatSessionRead | None:
        row = await self.session.get(ChatSession, session_id)
        if row is None:
            return None
        row.chat_name = chat_name
        await self.session.flush()
        await self.session.refresh(row)
        return ChatSessionRead.model_validate(row)

    async def delete(self, session_id: uuid.UUID) -> None:
        row = await self.session.get(ChatSession, session_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()
