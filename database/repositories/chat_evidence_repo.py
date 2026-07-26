from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ChatEvidence
from database.schemas import ChatEvidenceRead


class ChatEvidenceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_turn(
        self,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
        items: list[dict[str, Any]],
    ) -> list[ChatEvidenceRead]:
        await self.session.execute(
            delete(ChatEvidence).where(
                ChatEvidence.session_id == session_id,
                ChatEvidence.message_id == message_id,
            )
        )
        rows: list[ChatEvidence] = []
        for rank, item in enumerate(items):
            unit_id_raw = item.get("content_unit_id")
            unit_id = uuid.UUID(str(unit_id_raw)) if unit_id_raw else None
            metadata = dict(item.get("metadata") or {})
            for key in ("asset_name", "modality", "page_label", "timestamp", "bbox", "linked_media"):
                if key in item and key not in metadata:
                    metadata[key] = item[key]
            row = ChatEvidence(
                session_id=session_id,
                message_id=message_id,
                content_unit_id=unit_id,
                content=str(item.get("content") or ""),
                score=float(item.get("rerank_score") or item.get("score") or 0.0),
                base_vector_score=(
                    float(item["base_vector_score"])
                    if item.get("base_vector_score") is not None
                    else None
                ),
                metadata_=metadata,
                rank=rank,
                source=str(item.get("source") or "hybrid"),
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        for row in rows:
            await self.session.refresh(row)
        return [ChatEvidenceRead.model_validate(row) for row in rows]

    async def list_by_session(self, session_id: uuid.UUID) -> list[ChatEvidenceRead]:
        from sqlalchemy import select

        stmt = (
            select(ChatEvidence)
            .where(ChatEvidence.session_id == session_id)
            .order_by(ChatEvidence.rank.asc())
        )
        result = await self.session.execute(stmt)
        return [ChatEvidenceRead.model_validate(item) for item in result.scalars().all()]
