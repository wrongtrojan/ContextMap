"""Editable settings schema and public view builders."""

from __future__ import annotations

from typing import Any

from core.env import llm_api_key_configured, secret_hint

# Dot-paths allowed to be written via Settings UI.
EDITABLE_PATHS: dict[str, type] = {
    "outline.llm.model": str,
    "outline.llm.api_url": str,
    "outline.llm.timeout_sec": int,
    "pipeline.max_concurrent_parse": int,
    "pipeline.max_concurrent_whisper": int,
    "pipeline.max_concurrent_outline": int,
    "pipeline.max_concurrent_ingest": int,
    "pipeline.max_concurrent_kg": int,
    "pipeline.auto_start_on_upload": bool,
    "kg.enabled": bool,
    "kg.fail_open": bool,
    "kg.chunk_max_tokens": int,
    "retrieval.top_k_default": int,
    "retrieval.channels.graph.enabled": bool,
    "chat.research.max_retries": int,
    "chat.streaming.sse_token_batch_ms": int,
    "chat.streaming.sse_token_batch_chars": int,
}


def _get_nested(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def validate_changes(changes: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce change payload; raises ValueError on invalid paths/types."""
    if not changes:
        return {}
    normalized: dict[str, Any] = {}
    for path, raw in changes.items():
        if path not in EDITABLE_PATHS:
            raise ValueError(f"Path not editable: {path}")
        expected = EDITABLE_PATHS[path]
        if expected is bool:
            if isinstance(raw, bool):
                normalized[path] = raw
            elif isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered in ("true", "1", "yes", "on"):
                    normalized[path] = True
                elif lowered in ("false", "0", "no", "off"):
                    normalized[path] = False
                else:
                    raise ValueError(f"Invalid boolean for {path}")
            else:
                raise ValueError(f"Invalid boolean for {path}")
        elif expected is int:
            try:
                normalized[path] = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid integer for {path}") from exc
        elif expected is str:
            text = str(raw).strip()
            if not text:
                raise ValueError(f"Empty string not allowed for {path}")
            normalized[path] = text
        else:
            normalized[path] = raw
    return normalized


def apply_changes_to_dict(data: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    merged = dict(data)
    for path, value in changes.items():
        _set_nested(merged, path, value)
    return merged


def extract_editable_values(data: dict[str, Any]) -> dict[str, Any]:
    return {path: _get_nested(data, path) for path in EDITABLE_PATHS}


def get_public_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Build API-safe settings view (no secret values)."""
    outline_llm = (data.get("outline") or {}).get("llm") or {}
    pipeline = data.get("pipeline") or {}
    kg = data.get("kg") or {}
    retrieval = data.get("retrieval") or {}
    chat = data.get("chat") or {}
    graph_channel = (retrieval.get("channels") or {}).get("graph") or {}

    hint = secret_hint("DEEPSEEK_API_KEY")
    return {
        "llm": {
            "model": outline_llm.get("model"),
            "api_url": outline_llm.get("api_url"),
            "timeout_sec": outline_llm.get("timeout_sec"),
            "api_key_env": outline_llm.get("api_key_env") or "DEEPSEEK_API_KEY",
            "configured": llm_api_key_configured(),
            "hint": hint,
        },
        "pipeline": {
            "max_concurrent_parse": pipeline.get("max_concurrent_parse"),
            "max_concurrent_whisper": pipeline.get("max_concurrent_whisper"),
            "max_concurrent_outline": pipeline.get("max_concurrent_outline"),
            "max_concurrent_ingest": pipeline.get("max_concurrent_ingest"),
            "max_concurrent_kg": pipeline.get("max_concurrent_kg"),
            "auto_start_on_upload": pipeline.get("auto_start_on_upload"),
        },
        "kg": {
            "enabled": kg.get("enabled"),
            "fail_open": kg.get("fail_open"),
            "chunk_max_tokens": kg.get("chunk_max_tokens"),
        },
        "retrieval": {
            "top_k_default": retrieval.get("top_k_default"),
            "graph_enabled": graph_channel.get("enabled"),
        },
        "chat": {
            "max_retries": (chat.get("research") or {}).get("max_retries"),
            "streaming": dict(chat.get("streaming") or {}),
        },
        "editable_paths": list(EDITABLE_PATHS.keys()),
    }
