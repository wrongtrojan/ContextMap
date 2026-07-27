"""Settings API: read config from disk, save to YAML + secrets.env."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.settings.schema import get_public_settings
from core.settings.store import load_config_dict, save_settings

router = APIRouter()


class SettingsSaveRequest(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)
    deepseek_api_key: str | None = None


@router.get("")
async def get_settings():
    data = load_config_dict()
    return {
        "status": "success",
        "data": get_public_settings(data),
    }


@router.post("/save")
async def save_settings_endpoint(body: SettingsSaveRequest):
    try:
        result = save_settings(
            body.changes,
            deepseek_api_key=body.deepseek_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
