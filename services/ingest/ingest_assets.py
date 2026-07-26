"""
Ingest parsed assets into PostgreSQL + MinIO.

Examples:
  python -m services.ingest.ingest_assets --processed-dir storage/assets/processed/pdf/MyPaper
  python -m services.ingest.ingest_assets --scan
  python -m services.ingest.ingest_assets --scan --no-skip-if-ready
  python -m services.ingest.ingest_assets --processed-dir ... --repair-minio

After wiping Postgres (storage/db_data/postgres), run --scan to re-ingest all assets.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from database.enums import AssetModality, AssetStatus, ContentType
from database.repositories import AssetRepo, ContentUnitRepo
from database.schemas import AssetCreate, AssetRead, ContentUnitCreate, ContentUnitRead
from database.session import get_session
from paths import PROJECT_ROOT, modality_dirs
from services.common.processed_assets import (
    META_FILENAME,
    collect_processed_dirs,
    file_hash as meta_file_hash,
    middle_path as get_middle_path,
    read_meta,
    relative_path,
)
from services.ingest.embed import embed_texts
from services.ingest.fingerprint import build_ingest_fingerprint, ingest_fingerprints_match
from services.ingest.loaders import load_audio_units, load_pdf_units, load_video_units
from services.ingest.minio_client import (
    delete_prefix,
    get_minio_client,
    guess_content_type,
    load_minio_config,
    object_key_for_unit,
    upload_file,
)
from services.common.text_segment import segment_for_fts
from services.ingest.types import IngestUnit

MODALITY_DIRS = modality_dirs()


def _detect_modality(processed_dir: Path, meta: dict[str, Any]) -> AssetModality:
    modality = meta.get("modality")
    if modality == "video":
        return AssetModality.VIDEO
    if modality == "audio":
        return AssetModality.AUDIO
    parent = processed_dir.parent.name
    if parent == "video":
        return AssetModality.VIDEO
    if parent == "audio":
        return AssetModality.AUDIO
    return AssetModality.PDF


def _raw_path(meta: dict[str, Any], processed_dir: Path, modality: AssetModality) -> str:
    fingerprint = meta.get("fingerprint") or {}
    source = fingerprint.get("source_pdf") or fingerprint.get("source_name")
    if source:
        source_path = Path(source)
        if source_path.is_absolute():
            return relative_path(source_path, PROJECT_ROOT)
        return source
    if modality == AssetModality.PDF:
        pdf_name = fingerprint.get("pdf_name") or processed_dir.name
        return relative_path(PROJECT_ROOT / "storage" / "assets" / "raw" / "pdf" / pdf_name, PROJECT_ROOT)
    raw_dir = "video" if modality == AssetModality.VIDEO else "audio"
    source_name = fingerprint.get("source_name") or processed_dir.name
    return relative_path(PROJECT_ROOT / "storage" / "assets" / "raw" / raw_dir / source_name, PROJECT_ROOT)


def _load_units(
    processed_dir: Path,
    meta: dict[str, Any],
    modality: AssetModality,
) -> tuple[list[IngestUnit], dict[str, Any]]:
    middle_json_path = get_middle_path(processed_dir, meta)
    outputs = meta.get("outputs") or {}
    images_dir = processed_dir / (outputs.get("images_dir") or "images")

    if modality == AssetModality.PDF:
        units, stats = load_pdf_units(middle_json_path, images_dir)
        unreferenced = sorted(
            {
                path.name
                for path in images_dir.glob("*")
                if path.is_file()
            }
            - stats.referenced_images
        )
        coverage = {
            "block_types_seen": stats.block_types_seen,
            "units_by_type": stats.units_by_type,
            "disk_images": stats.disk_images,
            "referenced_images": len(stats.referenced_images),
            "minio_candidates": len(stats.uploaded_image_candidates),
            "unreferenced_disk_images": unreferenced,
        }
        return units, coverage
    if modality == AssetModality.VIDEO:
        units = load_video_units(middle_json_path, images_dir)
        frame_count = sum(1 for unit in units if unit.content_type == ContentType.FRAME)
        return units, {"units_by_type": {"transcript": len(units) - frame_count, "frame": frame_count}}
    units = load_audio_units(middle_json_path)
    return units, {"units_by_type": {"transcript": len(units)}}


def _asset_metadata(meta: dict[str, Any], ingest_fingerprint: dict[str, Any] | None = None) -> dict[str, Any]:
    fingerprint = meta.get("fingerprint") or {}
    payload: dict[str, Any] = {
        "parse_config": fingerprint.get("parse_config"),
        "parsed_at": meta.get("parsed_at"),
    }
    if ingest_fingerprint is not None:
        payload["ingest_fingerprint"] = ingest_fingerprint
    return payload


def _should_skip_ingest(
    existing: AssetRead | None,
    current_fingerprint: dict[str, Any],
    *,
    force: bool,
    skip_if_ready: bool,
) -> tuple[bool, str]:
    if force:
        return False, "force"
    if existing is None:
        return False, "no_asset"
    if not skip_if_ready:
        return False, "skip_if_ready_disabled"
    if existing.status != AssetStatus.READY:
        return False, "not_ready"
    stored = (existing.metadata or {}).get("ingest_fingerprint")
    if not stored:
        return False, "no_ingest_fingerprint"
    if ingest_fingerprints_match(stored, current_fingerprint):
        return True, "cache_hit"
    return False, "fingerprint_changed"


def _needs_minio(unit: IngestUnit) -> bool:
    return unit.local_blob_path is not None and unit.content_type in {
        ContentType.IMAGE,
        ContentType.TABLE,
        ContentType.FRAME,
    }


def _clear_minio_prefix(asset_id: uuid.UUID, modality: AssetModality, minio_cfg: dict[str, Any]) -> int:
    client = get_minio_client(minio_cfg)
    bucket = minio_cfg["bucket"]
    prefix = f"{modality.value}/{asset_id}/"
    return delete_prefix(client, bucket, prefix)


def _plan_minio_keys(
    units: list[IngestUnit],
    *,
    asset_id: uuid.UUID,
    modality: AssetModality,
    minio_cfg: dict[str, Any],
) -> list[IngestUnit]:
    bucket = minio_cfg["bucket"]
    modality_name = modality.value
    planned: list[IngestUnit] = []

    for unit in units:
        if not _needs_minio(unit):
            continue
        file_path = Path(unit.local_blob_path)
        if not file_path.exists():
            continue
        object_key = object_key_for_unit(
            minio_cfg,
            asset_uuid=str(asset_id),
            filename=file_path.name,
            modality=modality_name,
        )
        unit.metadata["minio_pending_key"] = object_key
        unit.metadata.setdefault("minio_bucket", bucket)
        planned.append(unit)
    return planned


def _apply_minio_uploads(
    units: list[IngestUnit],
    *,
    minio_cfg: dict[str, Any],
) -> tuple[int, list[str]]:
    client = get_minio_client(minio_cfg)
    bucket = minio_cfg["bucket"]
    uploaded = 0
    failures: list[str] = []

    for unit in units:
        pending_key = unit.metadata.get("minio_pending_key")
        if not pending_key:
            continue
        file_path = Path(unit.local_blob_path)
        if not file_path.exists():
            failures.append(f"missing_local:{file_path.name}")
            continue
        try:
            upload_file(
                client,
                bucket,
                pending_key,
                file_path,
                content_type=guess_content_type(file_path),
            )
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append(f"{file_path.name}:{exc}")
            continue

        if unit.content_type == ContentType.TABLE:
            unit.metadata.setdefault("table_text_ref", unit.content_ref)
        unit.content_ref = pending_key
        unit.metadata["minio_key"] = pending_key
        unit.metadata.pop("minio_pending_key", None)
        uploaded += 1

    return uploaded, failures


def _apply_embeddings(units: list[IngestUnit]) -> None:
    indices = [index for index, unit in enumerate(units) if unit.embed and unit.search_text.strip()]
    if not indices:
        return
    texts = [units[index].search_text for index in indices]
    vectors = embed_texts(texts)
    for idx, vector in zip(indices, vectors):
        units[idx].metadata["embedding_dim"] = len(vector)
        units[idx].metadata["_embedding"] = vector


def _units_to_payloads(asset_id: uuid.UUID, units: list[IngestUnit]) -> list[ContentUnitCreate]:
    payloads: list[ContentUnitCreate] = []
    for unit in units:
        embedding = unit.metadata.pop("_embedding", None)
        metadata = {key: value for key, value in unit.metadata.items() if key != "minio_pending_key"}
        payloads.append(
            ContentUnitCreate(
                asset_id=asset_id,
                content_type=unit.content_type,
                search_text=unit.search_text,
                search_tokens=unit.search_tokens or segment_for_fts(unit.search_text),
                content_ref=unit.content_ref,
                embedding=embedding,
                timestamp_anchor=unit.timestamp_anchor,
                chunk_index=unit.chunk_index,
                metadata=metadata,
            )
        )
    return payloads


def _summary_from_units(
    *,
    asset_id: uuid.UUID,
    modality: AssetModality,
    processed_rel: str,
    units: list[IngestUnit],
    created_units: list[ContentUnitRead],
    coverage: dict[str, Any],
    action: str,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "asset_id": str(asset_id),
        "modality": modality.value,
        "processed_path": processed_rel,
        "action": action,
        "skip_reason": skip_reason,
        "unit_count": len(created_units),
        "text_units": sum(1 for unit in units if unit.content_type == ContentType.TEXT),
        "image_units": sum(1 for unit in units if unit.content_type == ContentType.IMAGE),
        "table_units": sum(1 for unit in units if unit.content_type == ContentType.TABLE),
        "transcript_units": sum(1 for unit in units if unit.content_type == ContentType.TRANSCRIPT),
        "frame_units": sum(1 for unit in units if unit.content_type == ContentType.FRAME),
        "coverage": coverage,
    }


async def _upsert_asset_for_ingest(
    session,
    *,
    existing: AssetRead | None,
    asset_name: str,
    modality: AssetModality,
    raw_path: str,
    processed_rel: str,
    file_hash: str | None,
    file_size_bytes: int | None,
    base_metadata: dict[str, Any],
    preset_asset_id: uuid.UUID | None = None,
) -> uuid.UUID:
    asset_repo = AssetRepo(session)
    if existing is not None:
        await asset_repo.update_on_ingest(
            existing.id,
            name=asset_name,
            raw_path=raw_path,
            processed_path=processed_rel,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
            metadata=base_metadata,
            status=AssetStatus.INGESTING,
        )
        return existing.id

    if preset_asset_id is not None:
        preset = await asset_repo.get_by_id(preset_asset_id)
        if preset is not None:
            await asset_repo.update_on_ingest(
                preset_asset_id,
                name=asset_name,
                raw_path=raw_path,
                processed_path=processed_rel,
                file_size_bytes=file_size_bytes,
                file_hash=file_hash,
                metadata=base_metadata,
                status=AssetStatus.INGESTING,
            )
            return preset_asset_id

    created = await asset_repo.create(
        AssetCreate(
            name=asset_name,
            modality=modality,
            raw_path=raw_path,
            processed_path=processed_rel,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
            status=AssetStatus.INGESTING,
            metadata=base_metadata,
        ),
        asset_id=preset_asset_id,
    )
    return created.id


async def repair_minio_for_processed_dir(processed_dir: Path) -> dict[str, Any]:
    processed_dir = processed_dir.resolve()
    meta = read_meta(processed_dir)
    if meta.get("status") != "success":
        raise RuntimeError(f"Parse status is not success for {processed_dir}")

    modality = _detect_modality(processed_dir, meta)
    units, coverage = _load_units(processed_dir, meta, modality)
    minio_cfg = load_minio_config()
    source_hash = meta_file_hash(meta)

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        unit_repo = ContentUnitRepo(session)
        existing = await asset_repo.get_by_file_hash(source_hash) if source_hash else None
        if existing is None:
            raise RuntimeError(f"No ingested asset found for hash {source_hash}")
        asset_id = existing.id
        db_units = await unit_repo.list_by_asset(asset_id)

    db_by_chunk = {(unit.chunk_index, unit.content_type.value): unit for unit in db_units}
    minio_units: list[IngestUnit] = []
    for unit in units:
        if not _needs_minio(unit):
            continue
        key = (unit.chunk_index, unit.content_type.value)
        if key not in db_by_chunk:
            continue
        db_unit = db_by_chunk[key]
        unit.content_ref = db_unit.content_ref
        minio_units.append(unit)

    planned = _plan_minio_keys(minio_units, asset_id=asset_id, modality=modality, minio_cfg=minio_cfg)
    uploaded, failures = _apply_minio_uploads(planned, minio_cfg=minio_cfg)
    if failures:
        raise RuntimeError(f"MinIO repair failed: {failures}")

    async with get_session() as session:
        unit_repo = ContentUnitRepo(session)
        asset_repo = AssetRepo(session)
        updates = []
        for unit in planned:
            db_unit = db_by_chunk[(unit.chunk_index, unit.content_type.value)]
            updates.append((db_unit.id, unit.content_ref, unit.metadata))
        await unit_repo.bulk_update_content_refs(updates)
        await asset_repo.mark_ready(asset_id)

    return {
        "asset_id": str(asset_id),
        "action": "repair_minio",
        "minio_uploaded": uploaded,
        "coverage": coverage,
    }


def _coverage_from_meta(meta: dict[str, Any], modality: AssetModality) -> dict[str, Any]:
    stats = meta.get("stats") or {}
    if modality == AssetModality.AUDIO:
        count = int(stats.get("segment_count") or 0)
        return {"units_by_type": {"transcript": count}}
    if modality == AssetModality.VIDEO:
        seg = int(stats.get("segment_count") or 0)
        frames = int(stats.get("frame_count") or 0)
        return {"units_by_type": {"transcript": seg, "frame": frames}}
    return {}


async def ingest_processed_dir(
    processed_dir: Path,
    *,
    asset_id: uuid.UUID | None = None,
    skip_embed: bool = False,
    skip_minio: bool = False,
    force: bool = False,
    skip_if_ready: bool = True,
) -> dict[str, Any]:
    processed_dir = processed_dir.resolve()
    meta = read_meta(processed_dir)
    if meta.get("status") != "success":
        raise RuntimeError(f"Parse status is not success for {processed_dir}")

    modality = _detect_modality(processed_dir, meta)
    middle_json_path = get_middle_path(processed_dir, meta)
    minio_cfg = load_minio_config()

    source_hash = meta_file_hash(meta)
    asset_name = processed_dir.name
    raw_path = _raw_path(meta, processed_dir, modality)
    processed_rel = relative_path(processed_dir, PROJECT_ROOT)
    fingerprint = meta.get("fingerprint") or {}
    file_size_bytes = fingerprint.get("source_size") or fingerprint.get("pdf_size")
    base_metadata = _asset_metadata(meta)

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        if asset_id is not None:
            existing = await asset_repo.get_by_id(asset_id)
        else:
            existing = await asset_repo.get_by_file_hash(source_hash) if source_hash else None

    light_coverage = _coverage_from_meta(meta, modality)
    use_light_skip = bool(light_coverage.get("units_by_type"))
    skip = False
    skip_reason = "no_asset"
    if use_light_skip:
        ingest_fingerprint = build_ingest_fingerprint(meta, middle_json_path, light_coverage)
        skip, skip_reason = _should_skip_ingest(
            existing,
            ingest_fingerprint,
            force=force,
            skip_if_ready=skip_if_ready,
        )
        if skip and existing is not None:
            return _summary_from_units(
                asset_id=existing.id,
                modality=modality,
                processed_rel=processed_rel,
                units=[],
                created_units=[],
                coverage={**light_coverage, "skip_reason": skip_reason},
                action="skipped",
                skip_reason=skip_reason,
            )

    units, coverage = _load_units(processed_dir, meta, modality)
    ingest_fingerprint = build_ingest_fingerprint(meta, middle_json_path, coverage)
    if not skip:
        skip, skip_reason = _should_skip_ingest(
            existing,
            ingest_fingerprint,
            force=force,
            skip_if_ready=skip_if_ready,
        )
        if skip and existing is not None:
            return _summary_from_units(
                asset_id=existing.id,
                modality=modality,
                processed_rel=processed_rel,
                units=units,
                created_units=[],
                coverage={**coverage, "skip_reason": skip_reason},
                action="skipped",
                skip_reason=skip_reason,
            )

    resolved_asset_id: uuid.UUID | None = asset_id or (existing.id if existing is not None else None)
    try:
        if not skip_embed:
            _apply_embeddings(units)

        async with get_session() as session:
            unit_repo = ContentUnitRepo(session)
            if existing is not None:
                await unit_repo.delete_by_asset(existing.id)
            resolved_asset_id = await _upsert_asset_for_ingest(
                session,
                existing=existing,
                asset_name=asset_name,
                modality=modality,
                raw_path=raw_path,
                processed_rel=processed_rel,
                file_hash=source_hash,
                file_size_bytes=file_size_bytes,
                base_metadata=base_metadata,
                preset_asset_id=asset_id,
            )

            if not skip_minio and modality in {AssetModality.PDF, AssetModality.VIDEO}:
                removed = _clear_minio_prefix(resolved_asset_id, modality, minio_cfg)
                coverage["minio_removed"] = removed

            minio_units = (
                _plan_minio_keys(units, asset_id=resolved_asset_id, modality=modality, minio_cfg=minio_cfg)
                if not skip_minio
                else []
            )
            coverage["minio_planned"] = len(minio_units)

            payloads = _units_to_payloads(resolved_asset_id, units)
            created_units = await unit_repo.bulk_create(payloads)

        minio_uploaded = 0
        minio_failures: list[str] = []
        if not skip_minio and minio_units:
            minio_uploaded, minio_failures = _apply_minio_uploads(minio_units, minio_cfg=minio_cfg)
            coverage["minio_uploaded"] = minio_uploaded
            coverage["minio_failures"] = minio_failures
            if minio_failures:
                raise RuntimeError(f"MinIO upload failed for {len(minio_failures)} object(s): {minio_failures[:3]}")

            async with get_session() as session:
                unit_repo = ContentUnitRepo(session)
                db_units = await unit_repo.list_by_asset(resolved_asset_id)
                db_by_chunk = {(unit.chunk_index, unit.content_type.value): unit for unit in db_units}
                updates = []
                for unit in minio_units:
                    db_unit = db_by_chunk.get((unit.chunk_index, unit.content_type.value))
                    if db_unit is None:
                        continue
                    updates.append((db_unit.id, unit.content_ref, unit.metadata))
                await unit_repo.bulk_update_content_refs(updates)

        async with get_session() as session:
            asset_repo = AssetRepo(session)
            await asset_repo.mark_ready(
                resolved_asset_id,
                metadata=_asset_metadata(meta, ingest_fingerprint),
            )

        action = "reingested" if existing is not None else "created"
        return _summary_from_units(
            asset_id=resolved_asset_id,
            modality=modality,
            processed_rel=processed_rel,
            units=units,
            created_units=created_units,
            coverage=coverage,
            action=action,
        )
    except Exception as exc:
        if resolved_asset_id is not None:
            async with get_session() as session:
                asset_repo = AssetRepo(session)
                await asset_repo.mark_failed(resolved_asset_id, str(exc))
        raise


def _print_summary(processed_dir: Path, summary: dict[str, Any]) -> None:
    action = summary.get("action", "ingested")
    if action == "skipped":
        print(f"  [跳过] ingest_fingerprint 一致 ({summary.get('skip_reason')})")
        print(f"  asset={summary['asset_id']}")
        return

    print(
        f"  asset={summary['asset_id']} action={action} units={summary['unit_count']} "
        f"(text={summary['text_units']} image={summary['image_units']} "
        f"table={summary['table_units']} transcript={summary['transcript_units']} "
        f"frame={summary['frame_units']})"
    )
    coverage = summary.get("coverage") or {}
    if coverage:
        print(f"  coverage: {json.dumps(coverage, ensure_ascii=False)}")


async def _run(args: argparse.Namespace) -> int:
    if args.repair_minio:
        if not args.processed_dir:
            print("--repair-minio requires --processed-dir")
            return 1
        processed_dir = Path(args.processed_dir)
        print(f"Repairing MinIO: {processed_dir}")
        summary = await repair_minio_for_processed_dir(processed_dir)
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.scan:
        targets = collect_processed_dirs(MODALITY_DIRS)
    else:
        targets = collect_processed_dirs(MODALITY_DIRS, root=Path(args.processed_dir))

    if not targets:
        print("No processed asset directories found.")
        return 1

    results: list[dict[str, Any]] = []
    failures = 0
    for processed_dir in targets:
        print(f"Ingesting: {processed_dir}")
        try:
            summary = await ingest_processed_dir(
                processed_dir,
                skip_embed=args.skip_embed,
                skip_minio=args.skip_minio,
                force=args.force,
                skip_if_ready=not args.no_skip_if_ready,
            )
            results.append(summary)
            _print_summary(processed_dir, summary)
        except Exception as exc:
            failures += 1
            print(f"  [失败] {exc}")
            if not args.continue_on_error:
                return 1

    skipped = sum(1 for item in results if item.get("action") == "skipped")
    ingested = len(results) - skipped
    print(f"\nDone: ingested={ingested} skipped={skipped} failed={failures}")
    if args.force:
        print("幂等: 关闭 (--force)")
    elif not args.no_skip_if_ready:
        print("幂等: 开启 (默认 skip-if-ready)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest parsed assets into PostgreSQL + MinIO",
        epilog="After wiping Postgres (storage/db_data/postgres), run --scan to re-ingest all assets.",
    )
    parser.add_argument("--processed-dir", default=None, help="Single processed asset directory")
    parser.add_argument("--scan", action="store_true", help="Scan all processed pdf/video/audio directories")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding (debug)")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO upload (DB/embed only)")
    parser.add_argument("--force", action="store_true", help="Force re-ingest even when ingest_fingerprint matches")
    parser.add_argument(
        "--no-skip-if-ready",
        action="store_true",
        help="Disable skip-if-ready (always re-ingest unless unchanged checks are off)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="During --scan, continue after a single asset failure",
    )
    parser.add_argument(
        "--repair-minio",
        action="store_true",
        help="Re-upload blobs from processed dir and patch content_ref (requires --processed-dir)",
    )
    args = parser.parse_args()

    if not args.repair_minio and not args.scan and not args.processed_dir:
        parser.error("Provide --processed-dir or --scan")

    import asyncio

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
