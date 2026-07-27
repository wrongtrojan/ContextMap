"""Tests for parse idempotency: skip, failed meta retry, staging semantics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.parse.fingerprint import (
    META_FILENAME,
    build_pdf_fingerprint,
    load_meta,
    write_failed_meta,
)
from services.parse.parse_pdf import (
    _consolidate_output,
    output_paths,
    evaluate_skip,
    parse_one,
)
from tests.helpers.corpus_paths import AUTORE_DIR


def test_evaluate_skip_cache_hit_on_processed_sample() -> None:
    assert AUTORE_DIR.is_dir()
    meta = load_meta(AUTORE_DIR / META_FILENAME)
    assert meta is not None
    fingerprint = meta.get("fingerprint") or {}
    source_pdf = fingerprint.get("source_pdf")
    assert source_pdf
    pdf_path = Path(source_pdf)
    if not pdf_path.exists():
        pytest.skip(f"raw PDF missing: {pdf_path}")

    config = fingerprint.get("parse_config") or {}
    skip, paths, _stored_meta, reason, _fp = evaluate_skip(
        pdf_path,
        AUTORE_DIR.parent,
        config,
        force=False,
    )
    assert skip
    assert reason == "cache_hit"
    assert paths["middle"].is_file()


def test_failed_meta_written_and_retried(tmp_path: Path) -> None:
    pdf = tmp_path / "raw" / "demo.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF demo")
    out_root = tmp_path / "processed"
    out_root.mkdir()
    stem = pdf.stem
    final_dir = out_root / stem
    final_dir.mkdir()
    (final_dir / f"{stem}.md").write_text("# demo", encoding="utf-8")
    (final_dir / f"{stem}_middle.json").write_text('{"pdf_info":[]}', encoding="utf-8")

    config = {"lang": "ch", "backend": "pipeline", "parse_method": "auto"}
    fingerprint = build_pdf_fingerprint(pdf, config)
    meta_payload = {
        "status": "success",
        "fingerprint": fingerprint,
    }
    (final_dir / META_FILENAME).write_text(json.dumps(meta_payload), encoding="utf-8")

    skip, paths, _meta, reason, stored_fp = evaluate_skip(pdf, out_root, config, force=False)
    assert skip
    assert reason == "cache_hit"

    write_failed_meta(paths["meta"], stored_fp, "simulated failure")
    failed = load_meta(paths["meta"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == "simulated failure"

    skip_after_fail, _, _m, reason_after, _ = evaluate_skip(pdf, out_root, config, force=False)
    assert not skip_after_fail
    assert reason_after == "previous_failed"


def test_staging_atomic_replace(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    out_root = tmp_path / "out"
    out_root.mkdir()
    stem = pdf.stem
    paths = output_paths(out_root, stem)

    parse_dir = tmp_path / "mineru" / pdf.name / "auto"
    parse_dir.mkdir(parents=True)
    (parse_dir / f"{pdf.name}.md").write_text("# title", encoding="utf-8")
    (parse_dir / f"{pdf.name}_middle.json").write_text(
        '{"pdf_info":[{"para_blocks":[{"type":"text"}]}]}',
        encoding="utf-8",
    )

    final_dir = paths["dir"]
    final_dir.mkdir()
    (final_dir / f"{stem}.md").write_text("old", encoding="utf-8")

    fingerprint = {"pdf_sha256": "deadbeef", "parse_config": {}}
    middle, md, stats = _consolidate_output(
        parse_dir,
        pdf,
        paths,
        fingerprint,
        mineru_raw_dir=str(parse_dir),
    )
    assert middle.is_file()
    assert md.is_file()
    assert md.read_text(encoding="utf-8") == "# title"
    meta = json.loads((final_dir / META_FILENAME).read_text(encoding="utf-8"))
    assert meta["status"] == "success"
    assert meta["stats"]["pages"] == 1
    assert stats["text_blocks"] == 1
    assert not paths["staging"].exists()


def test_parse_one_failure_writes_failed_meta(tmp_path: Path) -> None:
    pdf = tmp_path / "fail.pdf"
    pdf.write_bytes(b"%PDF fail")
    out_root = tmp_path / "processed"
    out_root.mkdir()

    with patch("services.parse.parse_pdf._import_do_parse", side_effect=RuntimeError("mineru down")):
        with pytest.raises(RuntimeError, match="mineru down"):
            parse_one(pdf, out_root)

    meta = load_meta(out_root / pdf.stem / META_FILENAME)
    assert meta is not None
    assert meta["status"] == "failed"
    assert "mineru down" in meta["error_message"]
