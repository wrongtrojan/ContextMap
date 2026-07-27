"""Tests for Settings API and file persistence."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from httpx import ASGITransport, AsyncClient

from core.settings.store import load_config_dict, save_settings
from web.main import app


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def test_save_settings_writes_yaml(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "contextmap.yaml"
    src = Path(__file__).resolve().parents[1] / "configs" / "contextmap.yaml"
    cfg.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sec = tmp_path / "secrets.env"

    monkeypatch.chdir(tmp_path)

    result = save_settings(
        {"outline.llm.model": "test-model-save"},
        config_path=cfg,
        secrets_path=sec,
    )
    assert "contextmap.yaml" in result["saved_files"][0] or str(cfg.name) in result["saved_files"][0]

    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["outline"]["llm"]["model"] == "test-model-save"


def test_save_settings_writes_secret(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "contextmap.yaml"
    src = Path(__file__).resolve().parents[1] / "configs" / "contextmap.yaml"
    cfg.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sec = tmp_path / "secrets.env"

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    save_settings(
        {},
        deepseek_api_key="sk-test-secret-key",
        config_path=cfg,
        secrets_path=sec,
    )
    assert sec.is_file()
    assert "DEEPSEEK_API_KEY=sk-test-secret-key" in sec.read_text(encoding="utf-8")
    assert os.getenv("DEEPSEEK_API_KEY") == "sk-test-secret-key"


def test_save_rejects_non_whitelist_path(tmp_path: Path) -> None:
    cfg = tmp_path / "contextmap.yaml"
    src = Path(__file__).resolve().parents[1] / "configs" / "contextmap.yaml"
    cfg.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sec = tmp_path / "secrets.env"

    try:
        save_settings({"postgres.password": "hack"}, config_path=cfg, secrets_path=sec)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not editable" in str(exc)


async def test_settings_api_get_and_save(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "configs" / "contextmap.yaml"
    cfg.parent.mkdir(parents=True)
    src = Path(__file__).resolve().parents[1] / "configs" / "contextmap.yaml"
    cfg.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sec = tmp_path / "storage" / "local" / "secrets.env"

    import core.settings.store as store_mod

    monkeypatch.setattr(store_mod, "CONTEXTMAP_CONFIG", cfg)
    monkeypatch.setattr(store_mod, "LOCAL_SECRETS_ENV", sec)
    monkeypatch.setattr(store_mod, "PROJECT_ROOT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        get_res = await client.get("/api/v1/settings")
        assert get_res.status_code == 200
        body = get_res.json()
        assert body["status"] == "success"
        assert "llm" in body["data"]
        assert "configured" in body["data"]["llm"]

        save_res = await client.post(
            "/api/v1/settings/save",
            json={"changes": {"kg.enabled": True}},
        )
        assert save_res.status_code == 200
        saved = save_res.json()
        assert saved["status"] == "success"
        assert any("contextmap.yaml" in f for f in saved["saved_files"])

        reloaded = load_config_dict(cfg)
        assert reloaded["kg"]["enabled"] is True
