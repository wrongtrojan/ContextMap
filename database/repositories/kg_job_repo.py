from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import KgStatus
from database.models import KgJob


class KgJobRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_job(
        self,
        asset_id: uuid.UUID,
        *,
        status: KgStatus = KgStatus.EXTRACTING,
        chunks_total: int = 0,
    ) -> KgJob:
        job = await self.session.get(KgJob, asset_id)
        now = datetime.now(timezone.utc)
        if job is None:
            job = KgJob(
                asset_id=asset_id,
                status=status,
                chunks_total=chunks_total,
                chunks_processed=0,
                triples_extracted=0,
                started_at=now,
            )
            self.session.add(job)
        else:
            job.status = status
            job.chunks_total = chunks_total
            job.chunks_processed = 0
            job.triples_extracted = 0
            job.error_message = None
            job.started_at = now
            job.finished_at = None
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_by_asset(self, asset_id: uuid.UUID) -> KgJob | None:
        return await self.session.get(KgJob, asset_id)

    async def update_progress(
        self,
        asset_id: uuid.UUID,
        *,
        chunks_processed: int | None = None,
        triples_extracted: int | None = None,
    ) -> KgJob | None:
        job = await self.session.get(KgJob, asset_id)
        if job is None:
            return None
        if chunks_processed is not None:
            job.chunks_processed = chunks_processed
        if triples_extracted is not None:
            job.triples_extracted = triples_extracted
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def mark_status(
        self,
        asset_id: uuid.UUID,
        status: KgStatus,
        *,
        error_message: str | None = None,
        triples_extracted: int | None = None,
    ) -> KgJob | None:
        job = await self.session.get(KgJob, asset_id)
        if job is None:
            return None
        job.status = status
        job.error_message = error_message
        if triples_extracted is not None:
            job.triples_extracted = triples_extracted
        job.finished_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(job)
        return job
