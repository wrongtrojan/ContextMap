"""Optional LLM auditor for borderline evidence quality."""

from __future__ import annotations

from typing import Any

from services.evaluate.config import load_llm_config
from services.evaluate.prompts import render_prompt
from services.outline.llm import chat_json

_SYSTEM_PROMPT = "You are an academic evidence auditor. Respond with valid JSON only."


def _doc_view(evidence: dict) -> dict[str, Any]:
    metadata = dict(evidence.get("metadata") or {})
    return {
        "content": evidence.get("content"),
        "metadata": metadata,
    }


def evidence_has_video(evidence: list[dict]) -> bool:
    for item in evidence:
        metadata = item.get("metadata") or {}
        if metadata.get("modality") == "video":
            return True
        if metadata.get("type") in ("frame", "transcript"):
            return True
    return False


async def run_audit(
    *,
    query: str,
    evidence: list[dict],
    retry_index: int = 0,
) -> dict[str, Any]:
    user_prompt = render_prompt(
        "evidence_evaluator.jinja2",
        query=query,
        retry_index=retry_index,
        docs=[_doc_view(item) for item in evidence],
        any_video=evidence_has_video(evidence),
    )
    return await chat_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        config=load_llm_config(),
    )
