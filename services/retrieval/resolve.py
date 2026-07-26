"""Resolve retrieval preferences and content display."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo
from database.schemas import ContentUnitRead
from services.retrieval.types import RetrievalQuery


def parse_asset_status(raw: str | None) -> AssetStatus | None:
    if not raw:
        return None
    try:
        return AssetStatus(raw.lower())
    except ValueError:
        return None


def parse_modality(raw: str | None) -> AssetModality | None:
    if not raw:
        return None
    try:
        return AssetModality(raw.lower())
    except ValueError:
        return None


async def resolve_preferences(session: AsyncSession, query: RetrievalQuery) -> RetrievalQuery:
    asset_name = query.preferences.asset_name
    if asset_name and asset_name.lower() not in ("null", "none", ""):
        matches = await AssetRepo(session).find_by_name_ilike(asset_name, limit=1)
        if matches:
            query.resolved_asset_id = matches[0].id
    return query


def build_search_filters(query: RetrievalQuery, config: dict) -> dict:
    filters_cfg = config.get("filters") or {}
    status = parse_asset_status(filters_cfg.get("asset_status"))
    modality = parse_modality(query.preferences.modality)
    return {
        "asset_id": query.resolved_asset_id,
        "modality": modality,
        "asset_status": status,
    }


def display_content(unit: ContentUnitRead) -> str:
    if unit.content_type in (ContentType.IMAGE, ContentType.FRAME, ContentType.TABLE):
        return unit.search_text or unit.content_ref
    return unit.content_ref or unit.search_text


def page_label(unit: ContentUnitRead, modality: str) -> int | None:
    if modality == "pdf":
        meta = unit.metadata or {}
        if meta.get("page_label") is not None:
            return int(meta["page_label"])
        return int(unit.timestamp_anchor) if unit.timestamp_anchor else None
    return None


def timestamp_seconds(unit: ContentUnitRead, modality: str) -> float | None:
    if modality in ("video", "audio"):
        meta = unit.metadata or {}
        if meta.get("timestamp") is not None:
            return float(meta["timestamp"])
        if meta.get("start") is not None:
            return float(meta["start"])
        return float(unit.timestamp_anchor)
    return None
