from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AssetModality, AssetStatus, ContentType
from database.models import Asset, ContentUnit
from database.schemas import AssetRead, ContentUnitCreate, ContentUnitRead, VectorSearchResult
from services.common.text_segment import expand_query_tokens, segment_for_fts


class KeywordSearchResult:
    __slots__ = ("unit", "score", "fts_score", "ilike_score")

    def __init__(
        self,
        unit: ContentUnitRead,
        score: float,
        *,
        fts_score: float = 0.0,
        ilike_score: float = 0.0,
    ) -> None:
        self.unit = unit
        self.score = score
        self.fts_score = fts_score
        self.ilike_score = ilike_score


class ContentUnitRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _apply_filters(
        self,
        stmt,
        *,
        asset_id: uuid.UUID | None = None,
        modality: AssetModality | None = None,
        content_types: list[ContentType] | None = None,
        asset_status: AssetStatus | None = None,
    ):
        if asset_id is not None or modality is not None or asset_status is not None:
            stmt = stmt.join(Asset, ContentUnit.asset_id == Asset.id)
        if asset_id is not None:
            stmt = stmt.where(ContentUnit.asset_id == asset_id)
        if modality is not None:
            stmt = stmt.where(Asset.modality == modality)
        if asset_status is not None:
            stmt = stmt.where(Asset.status == asset_status)
        if content_types:
            stmt = stmt.where(ContentUnit.content_type.in_(content_types))
        return stmt

    async def bulk_create(self, payloads: list[ContentUnitCreate]) -> list[ContentUnitRead]:
        units = [
            ContentUnit(
                asset_id=payload.asset_id,
                content_type=payload.content_type,
                search_text=payload.search_text,
                search_tokens=payload.search_tokens,
                content_ref=payload.content_ref,
                embedding=payload.embedding,
                timestamp_anchor=payload.timestamp_anchor,
                chunk_index=payload.chunk_index,
                metadata_=payload.metadata,
            )
            for payload in payloads
        ]
        self.session.add_all(units)
        await self.session.flush()
        for unit in units:
            await self.session.refresh(unit)
        return [ContentUnitRead.model_validate(unit) for unit in units]

    async def bulk_update_content_refs(
        self,
        updates: list[tuple[uuid.UUID, str, dict[str, Any] | None]],
    ) -> None:
        if not updates:
            return
        unit_ids = [unit_id for unit_id, _, _ in updates]
        stmt = select(ContentUnit).where(ContentUnit.id.in_(unit_ids))
        result = await self.session.execute(stmt)
        by_id = {unit.id: unit for unit in result.scalars().all()}
        for unit_id, content_ref, metadata in updates:
            unit = by_id.get(unit_id)
            if unit is None:
                continue
            unit.content_ref = content_ref
            if metadata:
                unit.metadata_ = {**(unit.metadata_ or {}), **metadata}
        await self.session.flush()

    async def delete_by_asset(self, asset_id: uuid.UUID) -> int:
        from sqlalchemy import delete

        stmt = delete(ContentUnit).where(ContentUnit.asset_id == asset_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0

    async def list_by_asset(self, asset_id: uuid.UUID) -> list[ContentUnitRead]:
        stmt = (
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset_id)
            .order_by(ContentUnit.chunk_index, ContentUnit.content_type)
        )
        result = await self.session.execute(stmt)
        units = result.scalars().all()
        return [ContentUnitRead.model_validate(unit) for unit in units]

    async def get_by_ids(self, unit_ids: list[uuid.UUID]) -> list[ContentUnitRead]:
        if not unit_ids:
            return []
        stmt = select(ContentUnit).where(ContentUnit.id.in_(unit_ids))
        result = await self.session.execute(stmt)
        units = result.scalars().all()
        by_id = {unit.id: unit for unit in units}
        ordered = [by_id[uid] for uid in unit_ids if uid in by_id]
        return [ContentUnitRead.model_validate(unit) for unit in ordered]

    async def vector_search(
        self,
        query_embedding: list[float],
        *,
        limit: int = 5,
        asset_id: uuid.UUID | None = None,
        modality: AssetModality | None = None,
        content_types: list[ContentType] | None = None,
        asset_status: AssetStatus | None = None,
    ) -> list[VectorSearchResult]:
        distance = ContentUnit.embedding.cosine_distance(query_embedding)
        stmt = (
            select(ContentUnit, distance.label("distance"))
            .where(ContentUnit.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        stmt = self._apply_filters(
            stmt,
            asset_id=asset_id,
            modality=modality,
            content_types=content_types,
            asset_status=asset_status,
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            VectorSearchResult(
                unit=ContentUnitRead.model_validate(unit),
                score=1.0 - float(dist),
            )
            for unit, dist in rows
        ]

    async def keyword_search(
        self,
        *,
        query_text: str,
        keywords: list[str],
        limit: int = 40,
        asset_id: uuid.UUID | None = None,
        modality: AssetModality | None = None,
        content_types: list[ContentType] | None = None,
        asset_status: AssetStatus | None = None,
        fts_config: str = "simple",
        segment_chinese: bool = True,
    ) -> list[KeywordSearchResult]:
        cleaned_keywords = [k.strip() for k in keywords if k.strip()]
        query_text = query_text.strip()

        if segment_chinese:
            fts_query_text = segment_for_fts(query_text) if query_text else ""
            query_tokens = expand_query_tokens(query_text, *cleaned_keywords)
        else:
            fts_query_text = query_text
            query_tokens = cleaned_keywords

        indexed_text = func.coalesce(ContentUnit.search_tokens, ContentUnit.search_text)
        fts_vector = func.to_tsvector(fts_config, indexed_text)

        fts_score_expr = func.coalesce(
            func.ts_rank(
                fts_vector,
                func.plainto_tsquery(fts_config, fts_query_text or query_text),
            ),
            0.0,
        )

        stmt = select(ContentUnit, fts_score_expr.label("fts_score")).where(
            ContentUnit.search_text.is_not(None)
        )
        stmt = self._apply_filters(
            stmt,
            asset_id=asset_id,
            modality=modality,
            content_types=content_types,
            asset_status=asset_status,
        )

        if fts_query_text or query_text:
            match_clauses = [
                fts_vector.op("@@")(
                    func.plainto_tsquery(fts_config, fts_query_text or query_text)
                )
            ]
            if query_tokens:
                match_clauses.extend(
                    indexed_text.ilike(f"%{token}%") for token in query_tokens
                )
            elif cleaned_keywords:
                match_clauses.extend(
                    ContentUnit.search_text.ilike(f"%{kw}%") for kw in cleaned_keywords
                )
            stmt = stmt.where(or_(*match_clauses))
        elif query_tokens:
            stmt = stmt.where(or_(*[indexed_text.ilike(f"%{token}%") for token in query_tokens]))
        elif cleaned_keywords:
            stmt = stmt.where(
                or_(*[ContentUnit.search_text.ilike(f"%{kw}%") for kw in cleaned_keywords])
            )
        else:
            return []

        result = await self.session.execute(stmt)
        rows = result.all()

        scored: dict[uuid.UUID, KeywordSearchResult] = {}
        token_count = max(len(query_tokens), 1)

        for unit, fts_score in rows:
            haystack = (unit.search_tokens or unit.search_text or "").lower()
            raw_text = (unit.search_text or "").lower()
            ilike_hits = 0
            for token in query_tokens:
                token_lower = token.lower()
                if token_lower in haystack or token_lower in raw_text:
                    ilike_hits += 1
            ilike_score = ilike_hits / token_count
            combined = max(float(fts_score or 0.0), ilike_score)
            if combined <= 0:
                continue
            read = ContentUnitRead.model_validate(unit)
            existing = scored.get(unit.id)
            if existing is None or combined > existing.score:
                scored[unit.id] = KeywordSearchResult(
                    read,
                    combined,
                    fts_score=float(fts_score or 0.0),
                    ilike_score=ilike_score,
                )

        ordered = sorted(scored.values(), key=lambda item: item.score, reverse=True)
        return ordered[:limit]

    async def find_media_on_page(
        self,
        asset_id: uuid.UUID,
        *,
        page_label: int,
        content_types: list[ContentType],
    ) -> list[ContentUnitRead]:
        if not content_types:
            return []
        stmt = (
            select(ContentUnit)
            .where(
                ContentUnit.asset_id == asset_id,
                ContentUnit.content_type.in_(content_types),
            )
        )
        result = await self.session.execute(stmt)
        units = result.scalars().all()
        matched: list[ContentUnitRead] = []
        for unit in units:
            meta = unit.metadata_ or {}
            page = meta.get("page_label")
            if page is None:
                page = int(unit.timestamp_anchor) if unit.timestamp_anchor else None
            if page is not None and int(page) == int(page_label):
                matched.append(ContentUnitRead.model_validate(unit))
        return matched

    async def find_frames_near_timestamp(
        self,
        asset_id: uuid.UUID,
        *,
        timestamp: float,
        window_sec: float = 2.0,
    ) -> list[ContentUnitRead]:
        stmt = select(ContentUnit).where(
            ContentUnit.asset_id == asset_id,
            ContentUnit.content_type == ContentType.FRAME,
        )
        result = await self.session.execute(stmt)
        units = result.scalars().all()
        matched: list[ContentUnitRead] = []
        for unit in units:
            meta = unit.metadata_ or {}
            anchor = meta.get("timestamp")
            if anchor is None:
                anchor = unit.timestamp_anchor
            if anchor is None:
                continue
            if abs(float(anchor) - float(timestamp)) <= window_sec:
                matched.append(ContentUnitRead.model_validate(unit))
        return matched

    async def load_assets_for_units(self, unit_ids: list[uuid.UUID]) -> dict[uuid.UUID, AssetRead]:
        if not unit_ids:
            return {}
        stmt = (
            select(ContentUnit.id, Asset)
            .join(Asset, ContentUnit.asset_id == Asset.id)
            .where(ContentUnit.id.in_(unit_ids))
        )
        result = await self.session.execute(stmt)
        mapping: dict[uuid.UUID, AssetRead] = {}
        for unit_id, asset in result.all():
            mapping[unit_id] = AssetRead.model_validate(asset)
        return mapping
