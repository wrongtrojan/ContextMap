"""Shared parse utilities: fingerprint, meta I/O, time helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

META_FILENAME = "meta.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_failed_meta(meta_path: Path, fingerprint: dict[str, Any], error_message: str) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "failed",
        "failed_at": utc_now_iso(),
        "error_message": error_message,
        "fingerprint": fingerprint,
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def atomic_replace_staging(staging_dir: Path, final_dir: Path, stem: str) -> None:
    backup_dir = final_dir.parent / f".{stem}.backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    if final_dir.exists():
        final_dir.rename(backup_dir)

    try:
        staging_dir.rename(final_dir)
    except Exception:
        if backup_dir.exists() and not final_dir.exists():
            backup_dir.rename(final_dir)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)


def build_pdf_fingerprint(
    pdf_path: Path,
    parse_config: dict[str, Any],
    *,
    stored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stat = pdf_path.stat()
    fingerprint = {
        "source_pdf": str(pdf_path.resolve()),
        "pdf_name": pdf_path.name,
        "pdf_size": stat.st_size,
        "pdf_mtime": int(stat.st_mtime),
        "parse_config": parse_config,
    }
    if (
        stored
        and stored.get("pdf_size") == fingerprint["pdf_size"]
        and stored.get("pdf_mtime") == fingerprint["pdf_mtime"]
        and stored.get("pdf_sha256")
    ):
        fingerprint["pdf_sha256"] = stored["pdf_sha256"]
    else:
        fingerprint["pdf_sha256"] = sha256_file(pdf_path)
    return fingerprint


def build_media_fingerprint(
    source_path: Path,
    parse_config: dict[str, Any],
    *,
    stored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stat = source_path.stat()
    fingerprint = {
        "source_name": source_path.name,
        "source_size": stat.st_size,
        "source_mtime": int(stat.st_mtime),
        "parse_config": parse_config,
    }
    if (
        stored
        and stored.get("source_size") == fingerprint["source_size"]
        and stored.get("source_mtime") == fingerprint["source_mtime"]
        and stored.get("source_sha256")
    ):
        fingerprint["source_sha256"] = stored["source_sha256"]
    else:
        fingerprint["source_sha256"] = sha256_file(source_path)
    return fingerprint


def fingerprints_match(
    stored: dict[str, Any],
    current: dict[str, Any],
    keys: tuple[str, ...],
) -> bool:
    return all(stored.get(key) == current.get(key) for key in keys)


def should_skip(
    meta_path: Path,
    *,
    current_fingerprint: dict[str, Any],
    match_keys: tuple[str, ...],
    outputs_complete: Callable[[], bool],
    force: bool,
) -> tuple[bool, dict[str, Any] | None, str]:
    if force:
        return False, None, "force"

    meta = load_meta(meta_path)
    if meta is None:
        return False, None, "no_meta"

    if meta.get("status") != "success":
        reason = "previous_failed_or_incomplete"
        if meta.get("status") == "failed":
            reason = "previous_failed"
        return False, meta, reason

    if not outputs_complete():
        return False, meta, "outputs_missing"

    stored_fp = meta.get("fingerprint", {})
    if not fingerprints_match(stored_fp, current_fingerprint, match_keys):
        return False, meta, "fingerprint_changed"

    return True, meta, "cache_hit"


PDF_FINGERPRINT_KEYS = ("pdf_sha256", "pdf_size", "parse_config")
MEDIA_FINGERPRINT_KEYS = ("source_sha256", "source_size", "parse_config")
