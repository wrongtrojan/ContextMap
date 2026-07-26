"""Keyword retrieval channel (FTS + ILIKE)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories import ContentUnitRepo
from services.retrieval.resolve import build_search_filters
from services.retrieval.types import ChannelHit, RetrievalQuery


async def keyword_channel(
    session: AsyncSession,
    query: RetrievalQuery,
    *,
    config: dict,
) -> list[ChannelHit]:
    channels = config.get("channels") or {}
    if not channels.get("keyword", {}).get("enabled", True):
        return []
    if not query.keywords and not query.query_text:
        return []

    multiplier = int(config.get("candidate_multiplier", 5))
    limit = max(query.top_k * multiplier, query.top_k)
    filters = build_search_filters(query, config)
    keyword_cfg = config.get("keyword") or {}

    repo = ContentUnitRepo(session)
    hits = await repo.keyword_search(
        query_text=query.query_text,
        keywords=query.keywords,
        limit=limit,
        asset_id=filters["asset_id"],
        modality=filters["modality"],
        asset_status=filters["asset_status"],
        fts_config=str(keyword_cfg.get("fts_config", "simple")),
        segment_chinese=bool(keyword_cfg.get("segment_chinese", True)),
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
                channel="keyword",
                rank=rank,
                unit=item.unit,
                asset=asset,
            )
        )
    return channel_hits
