from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.chats.config import load_chat_config
from services.outline.llm import load_outline_config, resolve_api_key


def resolve_chat_llm_config() -> dict[str, Any]:
    chat_cfg = load_chat_config()
    llm_section = chat_cfg.get("llm") or {}
    if llm_section.get("inherit") == "outline":
        outline = load_outline_config()
        merged = dict(outline.get("llm") or {})
        merged.update({k: v for k, v in llm_section.items() if k != "inherit"})
        return merged
    return dict(llm_section)


async def stream_chat_completion(user_prompt: str, *, system_prompt: str = "") -> AsyncIterator[str]:
    llm_cfg = resolve_chat_llm_config()
    api_key = resolve_api_key(llm_cfg)
    timeout = float(llm_cfg.get("timeout_sec", 180))
    api_url = llm_cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    model = llm_cfg.get("model", "deepseek-chat")

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = {"model": model, "messages": messages, "stream": True}

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    yield delta
