"""Resolve local image paths from evidence metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from paths import ASSETS_DIR, PROJECT_ROOT


def resolve_image_path(evidence: dict[str, Any]) -> Path | None:
    metadata = evidence.get("metadata") or {}
    image_filename = metadata.get("image_filename")
    processed_path = metadata.get("processed_path")
    content_type = str(metadata.get("type") or "").lower()
    modality = str(metadata.get("modality") or "").lower()

    if not image_filename and not metadata.get("minio_key"):
        return None

    candidates: list[Path] = []

    if processed_path and image_filename:
        base = PROJECT_ROOT / processed_path if not Path(processed_path).is_absolute() else Path(processed_path)
        if content_type == "frame" or modality == "video":
            candidates.append(base / "frames" / str(image_filename))
        else:
            candidates.append(base / "images" / str(image_filename))
            candidates.append(base / str(image_filename))

    if image_filename and modality == "video":
        asset_name = metadata.get("asset_name")
        if asset_name:
            stem = Path(str(asset_name)).stem
            candidates.append(ASSETS_DIR / "processed" / "video" / stem / "frames" / str(image_filename))

    if image_filename:
        candidates.append(ASSETS_DIR / "processed" / "pdf" / str(image_filename))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    minio_key = metadata.get("minio_key")
    if minio_key:
        local = ASSETS_DIR / "minio_cache" / str(minio_key)
        if local.exists():
            return local

    return None
