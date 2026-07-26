"""Parse coverage statistics from middle.json artifacts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

_TEXT_BLOCK_TYPES = {"text", "title", "list", "index", "ref_text", "abstract"}


def _page_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    para_blocks = page.get("para_blocks") or []
    if para_blocks:
        return para_blocks
    return page.get("preproc_blocks") or []


def pdf_coverage_from_middle(middle_path: Path) -> dict[str, Any]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    block_types: Counter[str] = Counter()
    pages = 0
    for page in middle.get("pdf_info", []):
        pages += 1
        for block in _page_blocks(page):
            block_types[block.get("type") or "unknown"] += 1

    return {
        "pages": pages,
        "block_types_seen": dict(block_types),
        "text_blocks": sum(block_types.get(key, 0) for key in _TEXT_BLOCK_TYPES),
        "table_blocks": block_types.get("table", 0),
        "image_blocks": block_types.get("image", 0) + block_types.get("chart", 0),
    }


def media_coverage_from_middle(middle_path: Path) -> dict[str, Any]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    segments = middle.get("segments") or []
    images = middle.get("images") or []
    return {
        "duration_sec": middle.get("duration"),
        "segment_count": len(segments),
        "frame_count": len(images),
        "language": middle.get("language"),
        "modality": middle.get("modality"),
    }
