"""Tests for outline fingerprint helpers."""

from services.common.versions import LOADER_VERSION, OUTLINE_PROMPT_VERSION
from services.outline.fingerprint import (
    build_outline_fingerprint,
    outline_fingerprints_match,
)


def test_outline_fingerprint_match() -> None:
    current = {
        "middle_json_mtime": 1,
        "middle_json_size": 100,
        "md_mtime": 2,
        "md_size": 50,
        "prompt_version": OUTLINE_PROMPT_VERSION,
        "model_id": "deepseek-chat",
        "loader_version": LOADER_VERSION,
    }
    assert outline_fingerprints_match(current, dict(current))


def test_build_outline_fingerprint_from_paths(tmp_path) -> None:
    middle = tmp_path / "demo_middle.json"
    md = tmp_path / "demo.md"
    middle.write_text('{"pdf_info": []}', encoding="utf-8")
    md.write_text("# Title", encoding="utf-8")
    fp = build_outline_fingerprint(
        middle,
        md,
        prompt_version=OUTLINE_PROMPT_VERSION,
        model_id="deepseek-chat",
    )
    assert fp["middle_json_size"] > 0
    assert fp["md_mtime"] > 0
