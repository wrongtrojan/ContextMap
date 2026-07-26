"""Backward-compatible alias for transcript context loading."""

from __future__ import annotations

from services.outline.loaders.transcript_context import (
    TranscriptContextResult as VideoContextResult,
    TranscriptContextStats as VideoContextStats,
    load_transcript_context as load_video_context,
)

__all__ = ["VideoContextResult", "VideoContextStats", "load_video_context"]
