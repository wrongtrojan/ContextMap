from services.outline.loaders.pdf_context import load_pdf_context
from services.outline.loaders.transcript_context import (
    TranscriptContextResult,
    TranscriptContextStats,
    load_transcript_context,
)

AudioContextResult = TranscriptContextResult
AudioContextStats = TranscriptContextStats
VideoContextResult = TranscriptContextResult
VideoContextStats = TranscriptContextStats
load_audio_context = load_transcript_context
load_video_context = load_transcript_context

__all__ = [
    "AudioContextResult",
    "AudioContextStats",
    "VideoContextResult",
    "VideoContextStats",
    "load_audio_context",
    "load_pdf_context",
    "load_transcript_context",
    "load_video_context",
]
