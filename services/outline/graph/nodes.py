"""LangGraph nodes for outline generation."""

from __future__ import annotations

import json
from typing import Any

from services.outline.graph.state import OutlineState
from services.outline.llm import chat_json, load_outline_config
from services.outline.prompts import render_prompt, render_system_prompt
from services.outline.schema import validate_outline_payload


async def node_generate_draft(state: OutlineState) -> dict[str, Any]:
    user_prompt = render_prompt(
        "generate.jinja2",
        raw_context=state["raw_context"],
        modality=state["modality"],
    )
    draft = await chat_json(system_prompt=render_system_prompt(), user_prompt=user_prompt)
    return {"draft": draft, "errors": []}


async def node_validate_schema(state: OutlineState) -> dict[str, Any]:
    draft = state.get("draft") or {}
    parsed, errors = validate_outline_payload(
        draft,
        modality=state["modality"],
        max_anchor=state.get("max_anchor"),
    )
    if errors:
        return {"valid": False, "errors": errors, "title": parsed.title, "tree": []}
    tree = [node.model_dump() for node in parsed.outline]
    return {
        "valid": True,
        "errors": [],
        "title": parsed.title,
        "tree": tree,
        "failed": False,
        "failure_message": None,
    }


async def node_repair_json(state: OutlineState) -> dict[str, Any]:
    repair_count = int(state.get("repair_count") or 0) + 1
    user_prompt = render_prompt(
        "repair.jinja2",
        raw_context=state["raw_context"],
        modality=state["modality"],
        errors=state.get("errors") or [],
        draft_json=json.dumps(state.get("draft") or {}, ensure_ascii=False, indent=2),
    )
    draft = await chat_json(system_prompt=render_system_prompt(), user_prompt=user_prompt)
    return {"draft": draft, "repair_count": repair_count}


def route_after_validate(state: OutlineState) -> str:
    if state.get("valid"):
        return "done"
    repair_count = int(state.get("repair_count") or 0)
    max_retries = int(state.get("max_repair_retries") or load_outline_config()["graph"]["max_repair_retries"])
    if repair_count < max_retries:
        return "node_repair_json"
    return "node_mark_failed"


async def node_mark_failed(state: OutlineState) -> dict[str, Any]:
    errors = state.get("errors") or ["outline validation failed"]
    return {
        "failed": True,
        "failure_message": "; ".join(errors),
        "valid": False,
    }
