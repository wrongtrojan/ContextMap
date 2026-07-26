"""Tests for parse_audio module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.parse.fingerprint import META_FILENAME
from services.parse.parse_audio import (
    WhisperSegment,
    _build_settings,
    collect_audio,
    evaluate_skip,
    parse_one,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_AUDIO = PROJECT_ROOT / "storage/assets/raw/audio"


def test_collect_audio_filters_extensions(tmp_path: Path) -> None:
    (tmp_path / "clip.mp3").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")
    (tmp_path / "video.mp4").write_bytes(b"video")

    found = collect_audio(tmp_path)
    assert len(found) == 1
    assert found[0].name == "clip.mp3"


def test_collect_audio_rejects_video_container(tmp_path: Path) -> None:
    mp4 = tmp_path / "bad.mp4"
    mp4.write_bytes(b"video")
    with pytest.raises(ValueError, match="录音目录不接受视频容器"):
        collect_audio(mp4)


def test_evaluate_skip_cache_hit(tmp_path: Path) -> None:
    source = tmp_path / "clip.m4a"
    source.write_bytes(b"fake-audio")
    out_root = tmp_path / "processed"
    out_root.mkdir()
    stem = source.stem
    final_dir = out_root / stem
    final_dir.mkdir()
    (final_dir / f"{stem}.md").write_text("# transcript", encoding="utf-8")
    (final_dir / f"{stem}_middle.json").write_text(
        json.dumps({"modality": "audio", "duration": 1.0, "segments": []}),
        encoding="utf-8",
    )

    settings = _build_settings()
    fingerprint = {
        "source_name": source.name,
        "source_sha256": "abc",
        "source_size": len(b"fake-audio"),
        "parse_config": settings.to_fingerprint_dict(),
    }
    (final_dir / META_FILENAME).write_text(
        json.dumps({"status": "success", "fingerprint": fingerprint}),
        encoding="utf-8",
    )

    skip, paths, _meta, reason, _fp = evaluate_skip(source, out_root, settings, force=False)
    assert not skip
    assert reason in {"fingerprint_changed", "outputs_incomplete", "no_meta"}


def test_parse_one_mock_whisper(tmp_path: Path) -> None:
    source = tmp_path / "demo.m4a"
    source.write_bytes(b"fake-audio-content")
    out_root = tmp_path / "processed"

    segments = [
        WhisperSegment(start=0.0, end=1.5, text="hello world"),
        WhisperSegment(start=1.5, end=3.0, text="second segment"),
    ]

    with patch(
        "services.parse.parse_audio._transcribe",
        return_value=(segments, "zh", 3.0),
    ):
        middle, md, status, coverage = parse_one(
            source,
            out_root,
            allow_download=False,
        )

    assert status == "parsed"
    assert middle.is_file()
    assert md.is_file()
    middle_data = json.loads(middle.read_text(encoding="utf-8"))
    assert middle_data["modality"] == "audio"
    assert len(middle_data["segments"]) == 2
    assert coverage is not None
    assert coverage["segment_count"] == 2


@pytest.mark.skipif(not RAW_AUDIO.exists(), reason="raw audio dir missing")
def test_scan_raw_audio_has_csapp_sample() -> None:
    found = collect_audio(RAW_AUDIO)
    assert any(path.suffix.lower() == ".m4a" for path in found)
