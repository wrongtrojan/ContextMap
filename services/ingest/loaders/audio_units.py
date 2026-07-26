"""Load content units from audio middle.json."""

from __future__ import annotations

import json
from pathlib import Path

from database.enums import ContentType
from services.ingest.types import IngestUnit


def load_audio_units(middle_path: Path) -> list[IngestUnit]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    units: list[IngestUnit] = []
    chunk_index = 0

    for segment in middle.get("segments") or []:
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

    return units
