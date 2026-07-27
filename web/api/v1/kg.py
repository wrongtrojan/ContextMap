import uuid

from fastapi import APIRouter, HTTPException, Query

from database.session import get_session
from services.kg.subgraph import get_subgraph, search_entities
from web.api.deps import parse_asset_id

router = APIRouter()


@router.get("/subgraph")
async def kg_subgraph(
    scope: str = Query("full"),
    asset_id: str | None = Query(None),
    depth: int = Query(2, ge=1, le=3),
    limit: int = Query(500, ge=1, le=2000),
):
    asset_uuid: uuid.UUID | None = None
    if asset_id:
        asset_uuid = parse_asset_id(asset_id)
    if scope == "asset" and asset_uuid is None:
        raise HTTPException(status_code=400, detail="asset_id required when scope=asset")

    async with get_session() as session:
        if scope == "asset" and asset_uuid is not None:
            data = await get_subgraph(session, asset_id=asset_uuid, depth=depth)
        else:
            data = await get_subgraph(session, depth=depth, limit=limit)
    return {"status": "success", "data": data}


@router.get("/search")
async def kg_search(
    q: str = Query(..., min_length=1),
    asset_id: str | None = Query(None),
):
    asset_uuid: uuid.UUID | None = None
    if asset_id:
        asset_uuid = parse_asset_id(asset_id)
    async with get_session() as session:
        hits = await search_entities(session, q, asset_uuid)
    return {"status": "success", "data": hits}
