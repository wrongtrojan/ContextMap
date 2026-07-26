"""
Generate structured outlines from parsed assets into PostgreSQL.

Examples:
  python -m services.outline.generate_outline --processed-dir storage/assets/processed/pdf/MyPaper
  python -m services.outline.generate_outline --scan
  python -m services.outline.generate_outline --asset-id <uuid> --force
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from database.enums import AssetModality, AssetStatus
from database.repositories import AssetRepo, OutlineRepo
from database.schemas import AssetRead
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
from services.outline.fingerprint import (
    OUTLINE_PROMPT_VERSION,
    build_outline_fingerprint,
    outline_fingerprints_match,
)
from services.outline.graph import get_outline_graph
from services.outline.llm import load_outline_config
from services.outline.loaders import load_audio_context, load_pdf_context, load_video_context
from services.outline.persist import (
    default_export_filename,
    export_outline_json,
    persist_outline,
    should_export_json,
)
from services.outline.prompts import render_prompt

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


def _md_path(processed_dir: Path, meta: dict[str, Any]) -> Path | None:
    outputs = meta.get("outputs") or {}
    md_name = outputs.get("markdown") or outputs.get("transcript_md")
    if md_name:
        candidate = processed_dir / md_name
        if candidate.exists():
            return candidate
    candidates = list(processed_dir.glob("*.md"))
    return candidates[0] if candidates else None


def _load_context(
    processed_dir: Path,
    meta: dict[str, Any],
    modality: AssetModality,
    config: dict[str, Any],
) -> tuple[str, dict[str, Any], float | None]:
    middle_json_path = get_middle_path(processed_dir, meta)
    md_path = _md_path(processed_dir, meta)
    ctx_cfg = config.get("context") or {}
    max_chars = int(ctx_cfg.get("max_chars", 50000))

    if modality in {AssetModality.VIDEO, AssetModality.AUDIO}:
        loader = load_video_context if modality == AssetModality.VIDEO else load_audio_context
        result = loader(middle_json_path, max_chars=max_chars)
        coverage = {
            "segments": result.stats.segments,
            "truncated": result.stats.truncated,
            "duration_sec": result.stats.duration_sec,
            "context_chars": len(result.context),
        }
        return result.context, coverage, result.max_anchor

    result = load_pdf_context(
        middle_json_path,
        md_path,
        max_chars=max_chars,
        min_middle_lines=int(ctx_cfg.get("min_middle_lines", 5)),
        include_table_captions=bool(ctx_cfg.get("pdf_include_table_captions", True)),
    )
    coverage = {
        "lines": result.stats.lines,
        "pages": result.stats.pages,
        "truncated": result.stats.truncated,
        "used_md_fallback": result.stats.used_md_fallback,
        "context_chars": len(result.context),
    }
    return result.context, coverage, float(result.max_page)


def _should_skip_outline(
    asset: AssetRead | None,
    outline_exists: bool,
    current_fingerprint: dict[str, Any],
    *,
    force: bool,
    skip_if_ready: bool,
) -> tuple[bool, str]:
    if force:
        return False, "force"
    if asset is None:
        return False, "no_asset"
    if not skip_if_ready:
        return False, "skip_if_ready_disabled"
    if not outline_exists:
        return False, "no_outline"
    stored = (asset.metadata or {}).get("outline_fingerprint")
    if not stored:
        return False, "no_outline_fingerprint"
    if outline_fingerprints_match(stored, current_fingerprint):
        return True, "cache_hit"
    return False, "fingerprint_changed"


async def _resolve_asset(
    *,
    processed_dir: Path | None,
    asset_id: uuid.UUID | None,
    meta: dict[str, Any] | None,
) -> AssetRead | None:
    async with get_session() as session:
        repo = AssetRepo(session)
        if asset_id is not None:
            return await repo.get_by_id(asset_id)
        if processed_dir is not None:
            processed_rel = relative_path(processed_dir, PROJECT_ROOT)
            asset = await repo.get_by_processed_path(processed_rel)
            if asset is not None:
                return asset
            if meta is not None:
                source_hash = meta_file_hash(meta)
                if source_hash:
                    return await repo.get_by_file_hash(source_hash)
    return None


async def generate_outline_for_processed_dir(
    processed_dir: Path,
    *,
    force: bool = False,
    skip_if_ready: bool = True,
    dry_run: bool = False,
    export_json: bool | None = None,
    asset_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    processed_dir = processed_dir.resolve()
    meta = read_meta(processed_dir)
    if meta.get("status") != "success":
        raise RuntimeError(f"Parse status is not success for {processed_dir}")

    modality = _detect_modality(processed_dir, meta)

    config = load_outline_config()
    llm_cfg = config.get("llm") or {}
    prompt_version = (config.get("prompts") or {}).get("version") or OUTLINE_PROMPT_VERSION
    model_id = llm_cfg.get("model", "deepseek-chat")

    middle_json_path = get_middle_path(processed_dir, meta)
    md_path = _md_path(processed_dir, meta)
    outline_fp = build_outline_fingerprint(
        middle_json_path,
        md_path,
        prompt_version=prompt_version,
        model_id=model_id,
    )

    asset = await _resolve_asset(processed_dir=processed_dir, asset_id=asset_id, meta=meta)
    resolved_asset_id = asset.id if asset is not None else asset_id

    async with get_session() as session:
        outline_repo = OutlineRepo(session)
        existing_outline = (
            await outline_repo.get_by_asset(resolved_asset_id) if resolved_asset_id else None
        )

    skip, skip_reason = _should_skip_outline(
        asset,
        existing_outline is not None,
        outline_fp,
        force=force,
        skip_if_ready=skip_if_ready,
    )
    if skip and resolved_asset_id is not None:
        return {
            "asset_id": str(resolved_asset_id),
            "action": "skipped",
            "skip_reason": skip_reason,
            "modality": modality.value,
        }

    raw_context, coverage, max_anchor = _load_context(processed_dir, meta, modality, config)

    if dry_run:
        preview = render_prompt(
            "generate.jinja2",
            raw_context=raw_context[:2000],
            modality=modality.value,
        )
        return {
            "asset_id": str(resolved_asset_id) if resolved_asset_id else None,
            "action": "dry_run",
            "modality": modality.value,
            "coverage": coverage,
            "prompt_preview": preview[:2000],
        }

    if resolved_asset_id is None:
        raise RuntimeError(
            f"No asset in database for {processed_dir}. Run ingest first or pass --asset-id."
        )

    graph_cfg = config.get("graph") or {}
    initial_state = {
        "asset_id": str(resolved_asset_id),
        "modality": modality.value,
        "raw_context": raw_context,
        "max_anchor": max_anchor,
        "repair_count": 0,
        "max_repair_retries": int(graph_cfg.get("max_repair_retries", 2)),
        "model_id": model_id,
        "prompt_version": prompt_version,
    }

    async with get_session() as session:
        asset_repo = AssetRepo(session)
        current = await asset_repo.get_by_id(resolved_asset_id)
        if current is not None and current.status not in {AssetStatus.INGESTING}:
            await asset_repo.update_status(resolved_asset_id, AssetStatus.STRUCTURING)

    try:
        result = await get_outline_graph().ainvoke(initial_state)
        if result.get("failed") or not result.get("valid"):
            raise RuntimeError(result.get("failure_message") or "Outline generation failed")

        export_enabled = should_export_json(config=config, cli_export=export_json)
        export_path: Path | None = None

        async with get_session() as session:
            outline = await persist_outline(
                session,
                asset_id=resolved_asset_id,
                title=result.get("title"),
                tree=result.get("tree") or [],
                model_id=model_id,
                outline_fingerprint=outline_fp,
            )

        if export_enabled:
            export_path = export_outline_json(
                processed_dir,
                asset_id=resolved_asset_id,
                title=outline.title,
                tree=outline.tree,
                model_id=model_id,
                filename=default_export_filename(config),
            )

        summary: dict[str, Any] = {
            "asset_id": str(resolved_asset_id),
            "action": "generated",
            "modality": modality.value,
            "title": outline.title,
            "node_count": len(outline.tree),
            "repair_count": result.get("repair_count", 0),
            "coverage": coverage,
        }
        if export_path is not None:
            summary["export_path"] = str(export_path)
        return summary
    except Exception as exc:
        async with get_session() as session:
            asset_repo = AssetRepo(session)
            current = await asset_repo.get_by_id(resolved_asset_id)
            if current is not None and current.status != AssetStatus.INGESTING:
                await asset_repo.mark_failed(resolved_asset_id, str(exc))
        raise


async def _run(args: argparse.Namespace) -> int:
    if args.asset_id and args.processed_dir:
        print("Use either --asset-id or --processed-dir, not both")
        return 1

    targets: list[tuple[Path | None, uuid.UUID | None]] = []
    if args.asset_id:
        targets.append((None, uuid.UUID(args.asset_id)))
    elif args.scan:
        for processed_dir in collect_processed_dirs(MODALITY_DIRS):
            targets.append((processed_dir, None))
    else:
        targets.append((Path(args.processed_dir), None))

    if not targets:
        print("No processed asset directories found.")
        return 1

    results: list[dict[str, Any]] = []
    failures = 0
    for processed_dir, asset_id in targets:
        label = processed_dir or f"asset-id={asset_id}"
        print(f"Outlining: {label}")
        try:
            if processed_dir is not None:
                summary = await generate_outline_for_processed_dir(
                    processed_dir,
                    force=args.force,
                    skip_if_ready=not args.no_skip_if_ready,
                    dry_run=args.dry_run,
                    export_json=args.export_json if args.export_json else None,
                    asset_id=asset_id,
                )
            else:
                async with get_session() as session:
                    asset = await AssetRepo(session).get_by_id(asset_id)
                if asset is None or not asset.processed_path:
                    raise RuntimeError(f"Asset not found or missing processed_path: {asset_id}")
                summary = await generate_outline_for_processed_dir(
                    PROJECT_ROOT / asset.processed_path,
                    force=args.force,
                    skip_if_ready=not args.no_skip_if_ready,
                    dry_run=args.dry_run,
                    export_json=args.export_json if args.export_json else None,
                    asset_id=asset_id,
                )
            results.append(summary)
            if summary.get("action") == "skipped":
                print(f"  [跳过] outline_fingerprint 一致 ({summary.get('skip_reason')})")
                print(f"  asset={summary['asset_id']}")
            elif summary.get("action") == "dry_run":
                print(f"  dry_run context_chars={summary['coverage']['context_chars']}")
            else:
                print(
                    f"  asset={summary['asset_id']} action={summary['action']} "
                    f"nodes={summary.get('node_count')} title={summary.get('title')}"
                )
                if summary.get("coverage"):
                    print(f"  coverage: {json.dumps(summary['coverage'], ensure_ascii=False)}")
                if summary.get("export_path"):
                    print(f"  export: {summary['export_path']}")
        except Exception as exc:
            failures += 1
            print(f"  [失败] {exc}")
            if not args.continue_on_error:
                return 1

    skipped = sum(1 for item in results if item.get("action") == "skipped")
    generated = sum(1 for item in results if item.get("action") == "generated")
    print(f"\nDone: generated={generated} skipped={skipped} failed={failures}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate structured outlines into PostgreSQL")
    parser.add_argument("--processed-dir", default=None, help="Single processed asset directory")
    parser.add_argument("--asset-id", default=None, help="Existing asset UUID")
    parser.add_argument("--scan", action="store_true", help="Scan processed pdf/video/audio directories")
    parser.add_argument("--force", action="store_true", help="Force regeneration")
    parser.add_argument("--no-skip-if-ready", action="store_true", help="Disable skip-if-ready")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue batch on failure")
    parser.add_argument("--dry-run", action="store_true", help="Load context and preview prompt only")
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export summary_outline.json to processed dir (overrides config persist.export_json)",
    )
    args = parser.parse_args()

    if not args.scan and not args.processed_dir and not args.asset_id:
        parser.error("Provide --processed-dir, --asset-id, or --scan")

    import asyncio

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
