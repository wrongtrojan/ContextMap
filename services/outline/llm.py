"""LLM client and config for outline generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from paths import CONTEXTMAP_CONFIG

CONFIG_PATH = CONTEXTMAP_CONFIG

_LLM_CLIENT: httpx.AsyncClient | None = None


def _get_llm_client(timeout: float) -> httpx.AsyncClient:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = httpx.AsyncClient(timeout=timeout)
    return _LLM_CLIENT


def load_outline_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return dict(data.get("outline") or {})


def resolve_api_key(llm_cfg: dict[str, Any]) -> str:
    env_name = llm_cfg.get("api_key_env") or "DEEPSEEK_API_KEY"
    from_env = os.getenv(env_name)
    if from_env:
        return from_env.strip()
    raise RuntimeError(
        f"LLM API key not set: set env {env_name} in .env (see .env.example)"
    )


async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_outline_config()
    llm_cfg = cfg.get("llm") or {}
    api_key = resolve_api_key(llm_cfg)

    payload = {
        "model": llm_cfg.get("model", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    timeout = float(llm_cfg.get("timeout_sec", 120))
    api_url = llm_cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")

    client = _get_llm_client(timeout)
    response = await client.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    response.raise_for_status()
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
