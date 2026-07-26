"""Outline generation fingerprint helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.common.versions import LOADER_VERSION, OUTLINE_PROMPT_VERSION

__all__ = ["LOADER_VERSION", "OUTLINE_PROMPT_VERSION", "build_outline_fingerprint", "outline_fingerprints_match"]


def build_outline_fingerprint(
    middle_path: Path,
    md_path: Path | None,
    *,
    prompt_version: str,
    model_id: str,
) -> dict[str, Any]:
    middle_stat = middle_path.stat()
    md_mtime = int(md_path.stat().st_mtime) if md_path and md_path.exists() else 0
    md_size = md_path.stat().st_size if md_path and md_path.exists() else 0
    return {
        "middle_json_mtime": int(middle_stat.st_mtime),
        "middle_json_size": middle_stat.st_size,
        "md_mtime": md_mtime,
        "md_size": md_size,
        "prompt_version": prompt_version,
        "model_id": model_id,
        "loader_version": LOADER_VERSION,
    }


def outline_fingerprints_match(stored: dict[str, Any], current: dict[str, Any]) -> bool:
    keys = (
        "middle_json_mtime",
        "middle_json_size",
        "md_mtime",
        "md_size",
        "prompt_version",
        "model_id",
        "loader_version",
    )
    return all(stored.get(key) == current.get(key) for key in keys)
