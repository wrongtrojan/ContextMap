"""Tests for outline LangGraph nodes."""

from unittest.mock import AsyncMock, patch

import pytest

from services.outline.graph.nodes import (
    node_generate_draft,
    node_repair_json,
    node_validate_schema,
    route_after_validate,
)


@pytest.mark.asyncio
async def test_validate_schema_accepts_good_payload() -> None:
    state = {
        "modality": "pdf",
        "max_anchor": 10,
        "draft": {
            "title": "Demo",
            "outline": [
                {
                    "heading": "Intro",
                    "summary": "Intro summary",
                    "anchor": 1,
                    "sub_points": [],
                }
            ],
        },
    }
    result = await node_validate_schema(state)
    assert result["valid"] is True
    assert result["title"] == "Demo"
    assert route_after_validate({**state, **result}) == "done"


@pytest.mark.asyncio
async def test_repair_routes_back_to_validate() -> None:
    state = {"valid": False, "repair_count": 0, "max_repair_retries": 2, "errors": ["bad"]}
    assert route_after_validate(state) == "node_repair_json"


@pytest.mark.asyncio
async def test_generate_draft_calls_llm() -> None:
    with patch(
        "services.outline.graph.nodes.chat_json",
        new=AsyncMock(return_value={"title": "T", "outline": []}),
    ):
        result = await node_generate_draft(
            {"raw_context": "ctx", "modality": "pdf"},
        )
        assert result["draft"]["title"] == "T"


@pytest.mark.asyncio
async def test_repair_json_increments_counter() -> None:
    with patch(
        "services.outline.graph.nodes.chat_json",
        new=AsyncMock(return_value={"title": "T", "outline": []}),
    ):
        result = await node_repair_json(
            {
                "raw_context": "ctx",
                "modality": "pdf",
                "errors": ["x"],
                "draft": {"title": "bad"},
                "repair_count": 1,
            }
        )
        assert result["repair_count"] == 2
