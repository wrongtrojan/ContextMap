"""Isolated processed-dir copies for ingest integration tests.

Never run mock-embedding ingest against shared corpus directories (AutoRE, CSAPP).
Those paths back retrieval eval and live E2E; force reingest with fake vectors poisons PG.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from database.repositories import AssetRepo
from database.session import get_session

from tests.helpers.corpus_paths import AUTORE_DIR


def copy_processed_dir_for_test(
    source: Path,
    tmp_path: Path,
    *,
    hash_key: str = "pdf_sha256",
    prefix: str = "ingest-test",
) -> tuple[Path, str]:
    """Copy a processed asset dir and assign a unique file_hash for DB isolation."""
    dest = tmp_path / f"{prefix}-{uuid.uuid4().hex[:8]}"
    shutil.copytree(source, dest)
    meta_path = dest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fingerprint = dict(meta.get("fingerprint") or {})
    test_hash = f"{prefix}-{uuid.uuid4().hex}"
    fingerprint[hash_key] = test_hash
    meta["fingerprint"] = fingerprint
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest, test_hash


def copy_autore_for_ingest_test(tmp_path: Path) -> tuple[Path, str]:
    if not AUTORE_DIR.is_dir():
        raise FileNotFoundError(f"AutoRE sample missing: {AUTORE_DIR}")
    return copy_processed_dir_for_test(
        AUTORE_DIR,
        tmp_path,
        hash_key="pdf_sha256",
        prefix="autore-ingest-test",
    )


async def delete_asset_by_file_hash(file_hash: str | None) -> None:
    if not file_hash:
        return
    async with get_session() as session:
        repo = AssetRepo(session)
        asset = await repo.get_by_file_hash(file_hash)
        if asset is not None:
            await repo.delete(asset.id)
