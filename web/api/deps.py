"""FastAPI dependency helpers shared across v1 routers."""

from __future__ import annotations

import uuid

from fastapi import HTTPException


def parse_asset_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset_id UUID") from exc


def parse_session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID") from exc
