"""Query refinement via LLM."""

from __future__ import annotations

from services.outline.llm import chat_json
from services.retrieval.config import load_llm_config
from services.retrieval.prompts import render_prompt
from services.retrieval.types import RetrievalQuery

_SYSTEM_PROMPT = "You are an academic search strategist. Respond with valid JSON only."


async def refine_query(user_context: str) -> dict:
    """Render query_refiner prompt and call LLM → search_needs JSON."""
    user_prompt = render_prompt("query_refiner.jinja2", query=user_context)
    return await chat_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        config=load_llm_config(),
    )


def parse_search_needs(search_needs: dict) -> RetrievalQuery:
    return RetrievalQuery.from_search_needs(search_needs)
