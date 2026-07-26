"""Prepare sandbox requests via LLM."""

from __future__ import annotations

from typing import Any

from services.infer.config import load_llm_config
from services.infer.prompts import render_prompt
from services.infer.types import SandboxRequest
from services.outline.llm import chat_json

_SYSTEM_PROMPT = "You translate math problems into sandbox JSON instructions. Respond with valid JSON only."


def _build_context(evidence: list[dict]) -> str:
    chunks: list[str] = []
    for index, item in enumerate(evidence[:5], start=1):
        metadata = item.get("metadata") or {}
        header = metadata.get("asset_name") or metadata.get("asset_id") or f"doc-{index}"
        chunks.append(f"[{header}] {item.get('content')}")
    return "\n\n".join(chunks)


async def prepare_sandbox_request(*, query: str, evidence: list[dict]) -> SandboxRequest:
    user_prompt = render_prompt(
        "sandbox_prep.jinja2",
        query=query,
        context=_build_context(evidence),
    )
    payload: dict[str, Any] = await chat_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        config=load_llm_config(),
    )
    return SandboxRequest(
        expression=str(payload.get("expression") or ""),
        mode=str(payload.get("mode") or "eval"),
        symbol=str(payload.get("symbol") or "x"),
    )
