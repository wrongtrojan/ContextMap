"""Write extraction results to Apache AGE."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from services.kg.age_client import AgeClient
from services.kg.types import TextChunk, Triple


async def write_to_age(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    asset_name: str,
    modality: str,
    chunks: list[TextChunk],
    triples: list[Triple],
) -> int:
    client = AgeClient(session)
    return await client.write_asset_graph(
        asset_id=asset_id,
        asset_name=asset_name,
        modality=modality,
        chunks=chunks,
        triples=triples,
    )
