"""Knowledge-graph retrieval channel (fail-open)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories import ContentUnitRepo
from services.kg.age_client import AgeClient
from services.kg.config import load_kg_config
from services.retrieval.types import ChannelHit, RetrievalQuery


async def graph_channel(
    session: AsyncSession,
    query: RetrievalQuery,
    *,
    config: dict,
) -> tuple[list[ChannelHit], str | None, str | None]:
    """Returns (hits, skip_reason, error_message)."""
    channels = config.get("channels") or {}
    graph_cfg = channels.get("graph") or {}
    if not graph_cfg.get("enabled", True):
        return [], "graph.disabled", None

    kg_cfg = load_kg_config()
    if not kg_cfg.get("enabled", True):
        return [], "kg.disabled", None

    if not query.keywords:
        return [], "keywords.empty", None

    depth = int(graph_cfg.get("depth", 2))
    entity_limit = int(graph_cfg.get("entity_limit", 50))
    fail_open = bool(graph_cfg.get("fail_open", True))

    client = AgeClient(session)
    entity_names: list[str] = []
    try:
        for keyword in query.keywords:
            hits = await client.search_entities(keyword, query.resolved_asset_id)
            entity_names.extend(item["name"] for item in hits if item.get("name"))
        entity_names = list(dict.fromkeys(entity_names))[:entity_limit]
        if not entity_names:
            return [], "graph.empty", None

        resolved = await client.resolve_units_for_entities(
            entity_names,
            asset_id=query.resolved_asset_id,
            depth=depth,
            limit=entity_limit,
        )
        if not resolved:
            return [], "graph.no_units", None
    except Exception as exc:
        if fail_open:
            return [], None, str(exc)
        raise

    unit_ids: list[uuid.UUID] = []
    graph_meta: dict[uuid.UUID, dict] = {}
    for row in resolved:
        try:
            uid = uuid.UUID(str(row["unit_id"]))
        except ValueError:
            continue
        unit_ids.append(uid)
        graph_meta[uid] = row

    repo = ContentUnitRepo(session)
    units = await repo.get_by_ids(unit_ids)
    assets = await repo.load_assets_for_units(unit_ids)

    channel_hits: list[ChannelHit] = []
    for rank, unit in enumerate(units, start=1):
        asset = assets.get(unit.id)
        if asset is None:
            continue
        meta = graph_meta.get(unit.id, {})
        confidence = float(meta.get("confidence", 0.5))
        channel_hits.append(
            ChannelHit(
                unit_id=unit.id,
                score=confidence,
                channel="graph",
                rank=rank,
                unit=unit,
                asset=asset,
                graph_entity=str(meta.get("entity", "")),
                graph_hop=int(meta.get("hop", 0)),
            )
        )
    return channel_hits, None, None
