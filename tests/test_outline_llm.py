"""Tests for outline LLM config."""

import pytest

from services.outline.llm import resolve_api_key


def test_resolve_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    key = resolve_api_key({"api_key_env": "DEEPSEEK_API_KEY"})
    assert key == "env-key"


def test_resolve_api_key_missing() -> None:
    with pytest.raises(RuntimeError, match="LLM API key not set"):
        resolve_api_key({"api_key_env": "MISSING_ENV_FOR_OUTLINE_TEST"})
