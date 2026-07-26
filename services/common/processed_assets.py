"""Shared helpers for reading processed asset directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

META_FILENAME = "meta.json"


def relative_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(project_root.resolve()))
    except ValueError:
        return str(resolved)


def read_meta(processed_dir: Path) -> dict[str, Any]:
    with (processed_dir / META_FILENAME).open(encoding="utf-8") as handle:
        return json.load(handle)


def middle_path(processed_dir: Path, meta: dict[str, Any]) -> Path:
    outputs = meta.get("outputs") or {}
    middle_name = outputs.get("middle_json")
    if middle_name:
        return processed_dir / middle_name
    candidates = list(processed_dir.glob("*_middle.json"))
    if not candidates:
        raise FileNotFoundError(f"No middle.json found in {processed_dir}")
    return candidates[0]


def file_hash(meta: dict[str, Any]) -> str | None:
    fingerprint = meta.get("fingerprint") or {}
    return fingerprint.get("source_sha256") or fingerprint.get("pdf_sha256")


def collect_processed_dirs(
    modality_dirs: dict[str, Path],
    *,
    root: Path | None = None,
) -> list[Path]:
    if root is not None:
        if (root / META_FILENAME).exists():
            return [root]
        raise FileNotFoundError(f"No {META_FILENAME} in {root}")

    dirs: list[Path] = []
    for base in modality_dirs.values():
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and (child / META_FILENAME).exists():
                dirs.append(child)
    return dirs
