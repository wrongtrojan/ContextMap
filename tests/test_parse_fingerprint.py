"""Tests for shared parse fingerprint logic."""

from __future__ import annotations

from pathlib import Path

from services.parse.fingerprint import (
    PDF_FINGERPRINT_KEYS,
    build_media_fingerprint,
    build_pdf_fingerprint,
    fingerprints_match,
    should_skip,
)
from services.parse.parse_audio import ParseSettings, WhisperConfig, _build_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_MIDDLE = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
    / "Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models_middle.json"
)


def test_pdf_fingerprints_match_on_config() -> None:
    path = AUTORE_MIDDLE
    assert path.is_file()
    stored = {
        "pdf_sha256": "abc",
        "pdf_size": 123,
        "parse_config": {"lang": "ch", "backend": "pipeline", "parse_method": "auto"},
    }
    current = dict(stored)
    assert fingerprints_match(stored, current, PDF_FINGERPRINT_KEYS)
    current["parse_config"] = {"lang": "en", "backend": "pipeline", "parse_method": "auto"}
    assert not fingerprints_match(stored, current, PDF_FINGERPRINT_KEYS)


def test_build_pdf_fingerprint_includes_parse_config(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = {"lang": "ch", "backend": "pipeline", "parse_method": "auto"}
    fp = build_pdf_fingerprint(pdf, config)
    assert fp["pdf_name"] == "sample.pdf"
    assert fp["parse_config"] == config
    assert len(fp["pdf_sha256"]) == 64


def test_media_fingerprint_includes_initial_prompt(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake-audio")
    settings = _build_settings()
    assert settings.whisper is not None
    fp = build_media_fingerprint(media, settings.to_fingerprint_dict())
    whisper_fp = fp["parse_config"]["whisper"]
    assert "initial_prompt" in whisper_fp
    assert whisper_fp["initial_prompt"] == settings.whisper.initial_prompt


def test_initial_prompt_change_invalidates_fingerprint() -> None:
    base = ParseSettings(
        whisper=WhisperConfig(initial_prompt="prompt-a"),
    )
    changed = ParseSettings(
        whisper=WhisperConfig(initial_prompt="prompt-b"),
    )
    assert base.to_fingerprint_dict() != changed.to_fingerprint_dict()


def test_should_skip_force_bypasses_cache(tmp_path: Path) -> None:
    meta_path = tmp_path / "meta.json"
    meta_path.write_text('{"status":"success","fingerprint":{"pdf_sha256":"x"}}', encoding="utf-8")
    skip, _, reason = should_skip(
        meta_path,
        current_fingerprint={"pdf_sha256": "x", "pdf_size": 1, "parse_config": {}},
        match_keys=PDF_FINGERPRINT_KEYS,
        outputs_complete=lambda: True,
        force=True,
    )
    assert not skip
    assert reason == "force"


def test_should_skip_previous_failed(tmp_path: Path) -> None:
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        '{"status":"failed","error_message":"boom","fingerprint":{"pdf_sha256":"x"}}',
        encoding="utf-8",
    )
    skip, meta, reason = should_skip(
        meta_path,
        current_fingerprint={"pdf_sha256": "x", "pdf_size": 1, "parse_config": {}},
        match_keys=PDF_FINGERPRINT_KEYS,
        outputs_complete=lambda: True,
        force=False,
    )
    assert not skip
    assert meta is not None
    assert reason == "previous_failed"
