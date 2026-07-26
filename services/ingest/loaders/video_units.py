"""Load content units from video middle.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from database.enums import ContentType
from services.ingest.types import IngestUnit


def _segment_text_for_frame(segments: list[dict[str, Any]], filename: str) -> str:
    for segment in segments:
        for linked in segment.get("linked_images") or []:
            if linked.get("filename") == filename:
                return str(segment.get("text") or "")
    return ""


def _frame_text_lookup(segments: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for segment in segments:
        text = str(segment.get("text") or "")
        for linked in segment.get("linked_images") or []:
            filename = linked.get("filename")
            if filename:
                lookup[str(filename)] = text
    return lookup


def load_video_units(middle_path: Path, images_dir: Path) -> list[IngestUnit]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    units: list[IngestUnit] = []
    chunk_index = 0
    segments = middle.get("segments") or []
    frame_text = _frame_text_lookup(segments)

    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        units.append(
            IngestUnit(
                content_type=ContentType.TRANSCRIPT,
                search_text=text,
                content_ref=text,
                timestamp_anchor=float(segment.get("start") or 0.0),
                chunk_index=chunk_index,
                metadata={
                    "segment_index": segment.get("index"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                },
            )
        )
        chunk_index += 1

    frame_files = sorted(images_dir.glob("time_*.jpg")) if images_dir.exists() else []
    for frame_path in frame_files:
        filename = frame_path.name
        timestamp = float(filename.removeprefix("time_").removesuffix(".jpg"))
        search_text = frame_text.get(filename) or _segment_text_for_frame(segments, filename)
        if not search_text:
            search_text = f"[Frame at {timestamp:.2f}s]"
        units.append(
            IngestUnit(
                content_type=ContentType.FRAME,
                search_text=search_text,
                content_ref=filename,
                timestamp_anchor=timestamp,
                chunk_index=chunk_index,
                metadata={
                    "image_filename": filename,
                    "timestamp": timestamp,
                },
                local_blob_path=str(frame_path),
                embed=bool(search_text and not search_text.startswith("[Frame at")),
            )
        )
        chunk_index += 1

    return units
