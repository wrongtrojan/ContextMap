from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AssetStatus, PipelineEventType
from database.models import PipelineEvent


class PipelineEventRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        asset_id: uuid.UUID,
        event_type: PipelineEventType,
        *,
        step_name: str | None = None,
        from_status: AssetStatus | None = None,
        to_status: AssetStatus | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        event = PipelineEvent(
            asset_id=asset_id,
            event_type=event_type,
            step_name=step_name,
            from_status=from_status,
            to_status=to_status,
            detail=detail or {},
        )
        self.session.add(event)
        await self.session.flush()

    async def list_recent(
        self,
        asset_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[PipelineEvent]:
        stmt = (
            select(PipelineEvent)
            .where(PipelineEvent.asset_id == asset_id)
            .order_by(PipelineEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
