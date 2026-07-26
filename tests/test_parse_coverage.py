"""Tests for parse coverage statistics from processed samples."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.parse.asset_coverage import media_coverage_from_middle, pdf_coverage_from_middle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_MIDDLE = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
    / "Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models_middle.json"
)
CSAPP_MIDDLE = (
    PROJECT_ROOT
    / "storage/assets/processed/video/【CSAPP-深入理解计算机系统】2-1.信息的存储(上)"
    / "【CSAPP-深入理解计算机系统】2-1.信息的存储(上)_middle.json"
)


@pytest.mark.skipif(not AUTORE_MIDDLE.is_file(), reason="AutoRE processed sample missing")
def test_pdf_coverage_autore_sample() -> None:
    stats = pdf_coverage_from_middle(AUTORE_MIDDLE)
    assert stats["pages"] > 0
    assert stats["text_blocks"] > 0
    assert isinstance(stats["block_types_seen"], dict)
    assert stats["block_types_seen"]


@pytest.mark.skipif(not CSAPP_MIDDLE.is_file(), reason="CSAPP processed sample missing")
def test_video_coverage_csapp_sample() -> None:
    stats = media_coverage_from_middle(CSAPP_MIDDLE)
    assert stats["modality"] == "video"
    assert stats["segment_count"] > 0
    assert stats["duration_sec"] is not None
    assert stats["frame_count"] >= 0


def test_pdf_coverage_empty_middle(tmp_path: Path) -> None:
    middle = tmp_path / "empty_middle.json"
    middle.write_text('{"pdf_info":[]}', encoding="utf-8")
    stats = pdf_coverage_from_middle(middle)
    assert stats["pages"] == 0
    assert stats["text_blocks"] == 0
    assert stats["table_blocks"] == 0
