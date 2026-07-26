"""Expand text/transcript evidence with linked visual content units."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import ContentType
from database.repositories import ContentUnitRepo, AssetRepo
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
        asset = await asset_repo.get_by_id(asset_id)
        if asset is None:
            expanded.append(enriched)
            continue

        media_units: list[ContentUnitRead] = []
        if content_type == "text" and metadata.get("page_label") is not None:
            media_units = await repo.find_media_on_page(
                asset_id,
                page_label=int(metadata["page_label"]),
                content_types=[ContentType.IMAGE, ContentType.TABLE],
            )
        elif content_type == "transcript":
            ts = metadata.get("timestamp")
            if ts is not None:
                media_units = await repo.find_frames_near_timestamp(
                    asset_id,
                    timestamp=float(ts),
                    window_sec=window_sec,
                )
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
