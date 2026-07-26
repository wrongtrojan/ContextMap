"""Ingest fingerprint helpers for skip-if-unchanged idempotency."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.common.versions import LOADER_VERSION


def build_ingest_fingerprint(
    meta: dict[str, Any],
    middle_path: Path,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    stat = middle_path.stat()
    return {
        "middle_json_mtime": int(stat.st_mtime),
        "middle_json_size": stat.st_size,
        "loader_version": LOADER_VERSION,
        "unit_count_by_type": dict(coverage.get("units_by_type") or {}),
        "parse_parsed_at": meta.get("parsed_at"),
    }


def ingest_fingerprints_match(stored: dict[str, Any], current: dict[str, Any]) -> bool:
    keys = (
        "middle_json_mtime",
        "middle_json_size",
        "loader_version",
        "unit_count_by_type",
        "parse_parsed_at",
    )
    return all(stored.get(key) == current.get(key) for key in keys)
