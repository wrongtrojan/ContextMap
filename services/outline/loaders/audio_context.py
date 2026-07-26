"""Backward-compatible alias for audio transcript context loading."""

from __future__ import annotations

from services.outline.loaders.transcript_context import (
    TranscriptContextResult as AudioContextResult,
    TranscriptContextStats as AudioContextStats,
    load_transcript_context as load_audio_context,
)

__all__ = ["AudioContextResult", "AudioContextStats", "load_audio_context"]
