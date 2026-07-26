"""Vector retrieval channel."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories import ContentUnitRepo
from services.ingest.embed import embed_texts
from services.retrieval.resolve import build_search_filters
from services.retrieval.types import ChannelHit, RetrievalQuery


async def vector_channel(
    session: AsyncSession,
    query: RetrievalQuery,
    *,
    config: dict,
) -> list[ChannelHit]:
    channels = config.get("channels") or {}
    if not channels.get("vector", {}).get("enabled", True):
        return []
    if not query.semantic_query and not query.query_text:
        return []

    multiplier = int(config.get("candidate_multiplier", 5))
    limit = max(query.top_k * multiplier, query.top_k)
    filters = build_search_filters(query, config)

    embed_text = (query.semantic_query or query.query_text).strip()
    embedding = (await asyncio.to_thread(embed_texts, [embed_text]))[0]
    repo = ContentUnitRepo(session)
    hits = await repo.vector_search(
        embedding,
        limit=limit,
        asset_id=filters["asset_id"],
        modality=filters["modality"],
        asset_status=filters["asset_status"],
    )
    if not hits:
        return []

    unit_ids = [item.unit.id for item in hits]
    assets = await repo.load_assets_for_units(unit_ids)

    channel_hits: list[ChannelHit] = []
    for rank, item in enumerate(hits, start=1):
        asset = assets.get(item.unit.id)
        if asset is None:
            continue
        channel_hits.append(
            ChannelHit(
                unit_id=item.unit.id,
                score=item.score,
                channel="vector",
                rank=rank,
                unit=item.unit,
                asset=asset,
            )
        )
    return channel_hits
