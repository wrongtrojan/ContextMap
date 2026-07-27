"""Atomic read/write for configs/contextmap.yaml."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.settings.schema import (
    EDITABLE_PATHS,
    apply_changes_to_dict,
    extract_editable_values,
    get_public_settings,
    validate_changes,
)
from core.settings.secrets import apply_secret_hot_reload, upsert_secret
from paths import CONTEXTMAP_CONFIG, LOCAL_SECRETS_ENV, PROJECT_ROOT


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_config_dict(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _atomic_write_yaml(data: dict[str, Any], path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak")
    if path.is_file():
        shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)
    tmp.replace(path)


def _verify_changes(data: dict[str, Any], changes: dict[str, Any]) -> None:
    current = extract_editable_values(data)
    for path, expected in changes.items():
        actual = current.get(path)
        if actual != expected:
            raise RuntimeError(f"Read-back verify failed for {path}: expected {expected!r}, got {actual!r}")


def save_settings(
    changes: dict[str, Any],
    *,
    deepseek_api_key: str | None = None,
    config_path: Path | None = None,
    secrets_path: Path | None = None,
) -> dict[str, Any]:
    """
    Validate, persist YAML + optional secrets, verify read-back.

    Returns response payload with saved_files and public settings.
    """
    validated = validate_changes(changes)
    saved_files: list[str] = []
    cfg_path = config_path or CONTEXTMAP_CONFIG
    sec_path = secrets_path or LOCAL_SECRETS_ENV

    if validated:
        data = load_config_dict(cfg_path)
        merged = apply_changes_to_dict(data, validated)
        _atomic_write_yaml(merged, cfg_path)
        reloaded = load_config_dict(cfg_path)
        _verify_changes(reloaded, validated)
        saved_files.append(_display_path(cfg_path))

    key = (deepseek_api_key or "").strip()
    if key:
        upsert_secret("DEEPSEEK_API_KEY", key, sec_path)
        apply_secret_hot_reload("DEEPSEEK_API_KEY", key)
        reloaded_secrets = sec_path.read_text(encoding="utf-8")
        if "DEEPSEEK_API_KEY=" not in reloaded_secrets or key not in reloaded_secrets:
            raise RuntimeError("Read-back verify failed for DEEPSEEK_API_KEY")
        saved_files.append(_display_path(sec_path))

    if not saved_files:
        raise ValueError("No changes to save")

    public = get_public_settings(load_config_dict(cfg_path))
    return {
        "status": "success",
        "saved_files": saved_files,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "data": public,
        "editable_paths": list(EDITABLE_PATHS.keys()),
    }
