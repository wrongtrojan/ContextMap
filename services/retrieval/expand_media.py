"""Expand text/transcript evidence with linked visual content units."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import ContentUnitRead
from services.retrieval.resolve import display_content, page_label, timestamp_seconds


def _unit_to_evidence(unit: ContentUnitRead, asset) -> dict:
    modality = asset.modality.value
    meta = unit.metadata or {}
    image_filename = meta.get("image_filename")
    minio_key = meta.get("minio_key")
    return {
        "content_unit_id": str(unit.id),
        "score": 0.0,
        "content": display_content(unit),
        "metadata": {
            "asset_id": str(unit.asset_id),
            "asset_name": asset.name,
            "modality": modality,
            "type": unit.content_type.value,
            "timestamp": timestamp_seconds(unit, modality),
            "page_label": page_label(unit, modality),
            "image_filename": image_filename,
            "minio_key": minio_key,
            "minio_bucket": meta.get("minio_bucket"),
            "has_visual_asset": bool(image_filename or minio_key),
            "context_source": meta.get("context_source"),
            "processed_path": asset.processed_path,
            "linked_from_expand": True,
            "image_url": (
                f"/api/v1/assets/media/{image_filename}" if image_filename else None
            ),
            "bbox": meta.get("bbox"),
        },
    }


async def expand_linked_media(
    session: AsyncSession,
    evidence: list[dict],
    *,
    window_sec: float = 2.0,
) -> list[dict]:
    repo = ContentUnitRepo(session)
    asset_repo = AssetRepo(session)
    expanded: list[dict] = []
    seen_media: set[str] = set()

    asset_ids: set[uuid.UUID] = set()
    for item in evidence:
        asset_id_raw = (item.get("metadata") or {}).get("asset_id")
        if asset_id_raw:
            asset_ids.add(uuid.UUID(str(asset_id_raw)))

    assets = await asset_repo.get_by_ids(list(asset_ids))
    page_cache: dict[tuple[uuid.UUID, int], list[ContentUnitRead]] = {}
    frame_cache: dict[uuid.UUID, list[ContentUnitRead]] = {}

    async def _media_on_page(asset_id: uuid.UUID, page: int) -> list[ContentUnitRead]:
        key = (asset_id, page)
        if key not in page_cache:
            page_cache[key] = await repo.find_media_on_page(
                asset_id,
                page_label=page,
                content_types=[ContentType.IMAGE, ContentType.TABLE],
            )
        return page_cache[key]

    async def _frames_near(asset_id: uuid.UUID, timestamp: float) -> list[ContentUnitRead]:
        if asset_id not in frame_cache:
            frame_cache[asset_id] = await repo.find_frames_near_timestamp(
                asset_id,
                timestamp=timestamp,
                window_sec=window_sec,
            )
            return frame_cache[asset_id]
        units = frame_cache[asset_id]
        return [
            unit
            for unit in units
            if abs(float((unit.metadata or {}).get("timestamp") or unit.timestamp_anchor or 0) - timestamp)
            <= window_sec
        ]

    for item in evidence:
        enriched = dict(item)
        metadata = dict(item.get("metadata") or {})
        content_type = str(metadata.get("type") or "").lower()
        asset_id_raw = metadata.get("asset_id")
        linked: list[dict] = list(item.get("linked_media") or [])

        if not asset_id_raw:
            expanded.append(enriched)
            continue

        asset_id = uuid.UUID(str(asset_id_raw))
        asset = assets.get(asset_id)
        if asset is None:
            expanded.append(enriched)
            continue

        media_units: list[ContentUnitRead] = []
        if content_type == "text" and metadata.get("page_label") is not None:
            media_units = await _media_on_page(asset_id, int(metadata["page_label"]))
        elif content_type == "transcript":
            ts = metadata.get("timestamp")
            if ts is not None:
                media_units = await _frames_near(asset_id, float(ts))
        elif content_type in ("image", "frame", "table"):
            expanded.append(enriched)
            continue

        for unit in media_units:
            unit_id = str(unit.id)
            if unit_id in seen_media:
                continue
            seen_media.add(unit_id)
            media_evidence = _unit_to_evidence(unit, asset)
            linked.append(media_evidence)

        if linked:
            enriched["linked_media"] = linked
        expanded.append(enriched)

    return expanded
