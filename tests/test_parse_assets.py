"""Tests for parse_assets routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.parse.parse_assets import _resolve_input

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_AUDIO = PROJECT_ROOT / "storage/assets/raw/audio"


def test_resolve_input_routes_m4a_to_audio() -> None:
    sample = RAW_AUDIO / "【CSAPP-深入理解计算机系统】2-2.整数的表示(下).m4a"
    if not sample.is_file():
        pytest.skip("CSAPP audio sample not present")

    items = _resolve_input(sample, scan=False)
    assert len(items) == 1
    assert items[0][1] == "audio"


def test_resolve_input_rejects_mp4_in_raw_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_audio = tmp_path / "raw" / "audio"
    raw_audio.mkdir(parents=True)
    mp4 = raw_audio / "bad.mp4"
    mp4.write_bytes(b"video")

    import services.parse.parse_assets as parse_assets_module

    monkeypatch.setattr(parse_assets_module, "RAW_AUDIO_DIR", raw_audio)

    with pytest.raises(ValueError, match="录音目录不接受视频容器"):
        _resolve_input(mp4, scan=False)


def test_scan_includes_audio_when_present() -> None:
    if not RAW_AUDIO.is_dir():
        pytest.skip("raw audio dir missing")
    m4a_files = list(RAW_AUDIO.glob("*.m4a"))
    if not m4a_files:
        pytest.skip("no m4a in raw/audio")

    items = _resolve_input(None, scan=True)
    audio_items = [item for item in items if item[1] == "audio"]
    assert audio_items
