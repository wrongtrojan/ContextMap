"""Subgraph and entity search helpers."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from services.kg.age_client import AgeClient


async def get_subgraph(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID | None = None,
    depth: int = 2,
    limit: int = 500,
) -> dict:
    client = AgeClient(session)
    if asset_id:
        return await client.subgraph_by_asset(asset_id, depth=depth)
    return await client.subgraph_full(depth=depth, limit=limit)


async def search_entities(
    session: AsyncSession,
    query: str,
    asset_id: uuid.UUID | None = None,
) -> list[dict]:
    client = AgeClient(session)
    return await client.search_entities(query, asset_id=asset_id)
