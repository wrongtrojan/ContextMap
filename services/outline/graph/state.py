"""LangGraph state for outline generation."""

from __future__ import annotations

from typing import Any, TypedDict


class OutlineState(TypedDict, total=False):
    asset_id: str
    modality: str
    raw_context: str
    max_anchor: float | None
    draft: dict[str, Any] | None
    tree: list[dict[str, Any]]
    title: str | None
    errors: list[str]
    repair_count: int
    max_repair_retries: int
    model_id: str
    prompt_version: str
    valid: bool
    failed: bool
    failure_message: str | None
