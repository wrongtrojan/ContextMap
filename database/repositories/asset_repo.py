from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AssetStatus, KgStatus
from database.models import Asset
from database.schemas import AssetCreate, AssetRead


class AssetRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: AssetCreate, asset_id: uuid.UUID | None = None) -> AssetRead:
        asset = Asset(
            id=asset_id or uuid.uuid4(),
            name=payload.name,
            modality=payload.modality,
            status=payload.status,
            kg_status=payload.kg_status,
            raw_path=payload.raw_path,
            processed_path=payload.processed_path,
            file_size_bytes=payload.file_size_bytes,
            file_hash=payload.file_hash,
            metadata_=payload.metadata,
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def get_by_id(self, asset_id: uuid.UUID) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        return AssetRead.model_validate(asset) if asset else None

    async def get_by_file_hash(self, file_hash: str) -> AssetRead | None:
        stmt = select(Asset).where(Asset.file_hash == file_hash)
        result = await self.session.execute(stmt)
        asset = result.scalar_one_or_none()
        return AssetRead.model_validate(asset) if asset else None

    async def get_by_processed_path(self, processed_path: str) -> AssetRead | None:
        stmt = (
            select(Asset)
            .where(Asset.processed_path == processed_path)
            .order_by(Asset.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        asset = result.scalar_one_or_none()
        return AssetRead.model_validate(asset) if asset else None

    async def find_by_name_ilike(self, name: str, *, limit: int = 1) -> list[AssetRead]:
        pattern = name.strip()
        if not pattern:
            return []
        stmt = (
            select(Asset)
            .where(Asset.name.ilike(f"%{pattern}%"))
            .order_by(Asset.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [AssetRead.model_validate(item) for item in result.scalars().all()]

    async def update_status(self, asset_id: uuid.UUID, status: AssetStatus) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        asset.status = status
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def update_processed_path(
        self,
        asset_id: uuid.UUID,
        processed_path: str,
        *,
        status: AssetStatus | None = None,
    ) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        asset.processed_path = processed_path
        if status is not None:
            asset.status = status
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def list_all(self, limit: int = 500) -> list[AssetRead]:
        stmt = select(Asset).order_by(Asset.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [AssetRead.model_validate(item) for item in result.scalars().all()]

    async def update_on_ingest(
        self,
        asset_id: uuid.UUID,
        *,
        name: str,
        raw_path: str,
        processed_path: str | None,
        file_size_bytes: int | None,
        file_hash: str | None = None,
        metadata: dict[str, Any],
        status: AssetStatus = AssetStatus.INGESTING,
    ) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        asset.name = name
        asset.raw_path = raw_path
        asset.processed_path = processed_path
        asset.file_size_bytes = file_size_bytes
        if file_hash is not None:
            asset.file_hash = file_hash
        asset.metadata_ = {**(asset.metadata_ or {}), **metadata}
        asset.status = status
        asset.error_message = None
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def mark_ready(self, asset_id: uuid.UUID, metadata: dict[str, Any] | None = None) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        if metadata:
            asset.metadata_ = {**(asset.metadata_ or {}), **metadata}
        asset.status = AssetStatus.READY
        asset.error_message = None
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def mark_failed(self, asset_id: uuid.UUID, error_message: str) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        asset.status = AssetStatus.FAILED
        asset.error_message = error_message
        asset.retry_count += 1
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def update_kg_status(
        self,
        asset_id: uuid.UUID,
        kg_status: KgStatus,
        *,
        triple_count: int | None = None,
    ) -> AssetRead | None:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return None
        asset.kg_status = kg_status
        if triple_count is not None:
            asset.triple_count = triple_count
        await self.session.flush()
        await self.session.refresh(asset)
        return AssetRead.model_validate(asset)

    async def delete(self, asset_id: uuid.UUID) -> bool:
        asset = await self.session.get(Asset, asset_id)
        if asset is None:
            return False
        await self.session.delete(asset)
        await self.session.flush()
        return True
