from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Outline
from database.schemas import OutlineCreate, OutlineRead


class OutlineRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_asset(self, asset_id: uuid.UUID) -> OutlineRead | None:
        outline = await self.session.get(Outline, asset_id)
        return OutlineRead.model_validate(outline) if outline else None

    async def upsert(self, payload: OutlineCreate) -> OutlineRead:
        now = datetime.now(timezone.utc)
        stmt = (
            insert(Outline)
            .values(
                asset_id=payload.asset_id,
                title=payload.title,
                tree=payload.tree,
                model_id=payload.model_id,
                generated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[Outline.asset_id],
                set_={
                    "title": payload.title,
                    "tree": payload.tree,
                    "model_id": payload.model_id,
                    "generated_at": now,
                },
            )
            .returning(Outline)
        )
        result = await self.session.execute(stmt)
        outline = result.scalar_one()
        await self.session.flush()
        await self.session.refresh(outline)
        return OutlineRead.model_validate(outline)

    async def delete_by_asset(self, asset_id: uuid.UUID) -> bool:
        outline = await self.session.get(Outline, asset_id)
        if outline is None:
            return False
        await self.session.delete(outline)
        await self.session.flush()
        return True
