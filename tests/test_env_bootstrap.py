"""Tests for core.env bootstrap."""

from __future__ import annotations

import os

from core.env import load_dotenv, llm_api_key_configured


def test_load_dotenv_sets_key_from_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key-from-file\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_dotenv(tmp_path)
    assert os.getenv("DEEPSEEK_API_KEY") == "test-key-from-file"
    assert llm_api_key_configured()


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "existing")
    load_dotenv(tmp_path)
    assert os.getenv("DEEPSEEK_API_KEY") == "existing"


def test_load_secrets_sets_key_from_storage(tmp_path, monkeypatch) -> None:
    secrets_dir = tmp_path / "storage" / "local"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "secrets.env").write_text("DEEPSEEK_API_KEY=from-secrets\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from core.env import load_secrets

    load_secrets(tmp_path)
    assert os.getenv("DEEPSEEK_API_KEY") == "from-secrets"
