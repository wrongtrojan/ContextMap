"""Tests for outline context loaders."""

import json
from pathlib import Path

import pytest

from services.outline.loaders.pdf_context import load_pdf_context
from services.outline.loaders.video_context import load_video_context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_DIR = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
)
VIDEO_DIR = PROJECT_ROOT / "storage/assets/processed/video/【CSAPP-深入理解计算机系统】2-1.信息的存储(上)"


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
def test_pdf_context_has_page_markers() -> None:
    middle = next(AUTORE_DIR.glob("*_middle.json"))
    md = next(AUTORE_DIR.glob("*.md"))
    result = load_pdf_context(middle, md, max_chars=50000)
    assert "[p" in result.context
    assert result.stats.lines > 0


@pytest.mark.skipif(not VIDEO_DIR.exists(), reason="CSAPP video sample not present")
def test_video_context_has_timestamps() -> None:
    middle = next(VIDEO_DIR.glob("*_middle.json"))
    result = load_video_context(middle, max_chars=50000)
    assert "[t=" in result.context
    assert result.stats.segments > 0
    assert result.stats.duration_sec > 0
    assert result.max_anchor > 0


def _find_processed_audio_dir() -> Path | None:
    audio_root = PROJECT_ROOT / "storage/assets/processed/audio"
    if not audio_root.is_dir():
        return None
    for path in sorted(audio_root.iterdir()):
        if path.is_dir() and any(path.glob("*_middle.json")):
            return path
    return None


AUDIO_DIR = _find_processed_audio_dir() or PROJECT_ROOT / "storage/assets/processed/audio/_missing"


@pytest.mark.skipif(not AUDIO_DIR.exists(), reason="CSAPP audio sample not present")
def test_audio_context_has_timestamps() -> None:
    from services.outline.loaders.audio_context import load_audio_context

    middle = next(AUDIO_DIR.glob("*_middle.json"))
    result = load_audio_context(middle, max_chars=50000)
    assert "[t=" in result.context
    assert result.stats.segments > 0
    assert result.stats.duration_sec > 0
    assert result.max_anchor > 0


def test_transcript_loaders_share_implementation() -> None:
    from services.outline.loaders.transcript_context import load_transcript_context

    middle = {
        "modality": "audio",
        "duration": 12.5,
        "segments": [{"start": 1.0, "end": 2.0, "text": "hello"}],
    }
    path = Path("dummy_middle.json")
    path.write_text(json.dumps(middle), encoding="utf-8")
    try:
        result = load_transcript_context(path, max_chars=1000)
        assert result.context == "[t=1.00s] hello"
        assert result.max_anchor == 12.5
    finally:
        path.unlink()
