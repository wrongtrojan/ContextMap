"""Load condensed transcript context from video/audio middle.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptContextStats:
    segments: int = 0
    truncated: bool = False
    duration_sec: float = 0.0


@dataclass
class TranscriptContextResult:
    context: str
    stats: TranscriptContextStats = field(default_factory=TranscriptContextStats)
    max_anchor: float = 0.0


def load_transcript_context(middle_path: Path, *, max_chars: int) -> TranscriptContextResult:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    duration = float(middle.get("duration") or 0.0)
    lines: list[str] = []
    max_segment_start = 0.0
    for segment in middle.get("segments", []):
        start = float(segment.get("start", 0.0))
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        max_segment_start = max(max_segment_start, start)
        lines.append(f"[t={start:.2f}s] {text}")

    context = "\n".join(lines)
    stats = TranscriptContextStats(
        segments=len(lines),
        duration_sec=duration,
    )
    if len(context) > max_chars:
        context = context[:max_chars]
        stats.truncated = True

    max_anchor = duration if duration > 0 else max_segment_start
    if max_segment_start > max_anchor:
        max_anchor = max_segment_start

    return TranscriptContextResult(context=context, stats=stats, max_anchor=max_anchor)
