"""
KG extraction for a single asset.

首次真实抽取（非 --mock）会自动从魔搭下载 Mistral 基座、从 HuggingFace 下载 LoRA 适配器到
configs/contextmap.yaml 的 kg.autore.model_dir（默认 models/autore/）。

Usage:
  python -m services.kg.extract_assets --asset-id <uuid>
  python -m services.kg.extract_assets --asset-id <uuid> --dry-run
  python -m services.kg.extract_assets --asset-id <uuid> --mock
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

from database.enums import KgStatus
from database.repositories import AssetRepo, KgJobRepo
from database.session import get_session
from services.kg.age_writer import write_to_age
from services.kg.chunker import collect_chunks
from services.kg.config import load_kg_config
from services.kg.extract_rhf import extract_triples_from_chunk, extract_triples_mock
from services.kg.autore_runtime import ensure_autore_models, config_from_yaml
from services.kg.types import ExtractionResult, Triple

logger = logging.getLogger("KGExtract")


async def extract_kg_for_asset(
    asset_id: uuid.UUID,
    *,
    dry_run: bool = False,
    use_mock: bool = False,
    allow_download: bool = True,
) -> dict:
    cfg = load_kg_config()
    if not cfg.get("enabled", True):
        async with get_session() as session:
            await AssetRepo(session).update_kg_status(asset_id, KgStatus.SKIPPED)
        return {"action": "skipped", "reason": "kg.disabled"}

    autore_cfg = cfg.get("autore") or {}
    if not autore_cfg.get("auto_download", True):
        allow_download = False

    async with get_session() as session:
        asset = await AssetRepo(session).get_by_id(asset_id)
        if asset is None:
            raise ValueError(f"Asset not found: {asset_id}")
        modality = asset.modality.value
        asset_name = asset.name

    chunks = await collect_chunks(asset_id, modality)
    if dry_run:
        return {
            "action": "dry_run",
            "asset_id": str(asset_id),
            "chunks": len(chunks),
        }

    if not use_mock:
        logger.info(
            "Checking AutoRE models (first run auto-downloads to %s)",
            config_from_yaml().model_dir,
        )
        await asyncio.to_thread(
            ensure_autore_models,
            config_from_yaml(),
            allow_download=allow_download,
        )

    async with get_session() as session:
        await KgJobRepo(session).upsert_job(asset_id, chunks_total=len(chunks))
        await AssetRepo(session).update_kg_status(asset_id, KgStatus.EXTRACTING)

    all_triples: list[Triple] = []
    for index, chunk in enumerate(chunks, start=1):
        if use_mock:
            triples = extract_triples_mock(chunk)
        else:
            try:
                triples = extract_triples_from_chunk(chunk, allow_download=allow_download)
            except Exception as exc:
                logger.warning("Chunk %s extraction failed: %s", index, exc)
                triples = []
        all_triples.extend(triples)
        async with get_session() as session:
            await KgJobRepo(session).update_progress(
                asset_id,
                chunks_processed=index,
                triples_extracted=len(all_triples),
            )

    triple_count = 0
    status = KgStatus.READY
    error_message: str | None = None
    try:
        async with get_session() as session:
            triple_count = await write_to_age(
                session,
                asset_id=asset_id,
                asset_name=asset_name,
                modality=modality,
                chunks=chunks,
                triples=all_triples,
            )
    except Exception as exc:
        logger.exception("AGE write failed for %s", asset_id)
        status = KgStatus.FAILED if not all_triples else KgStatus.PARTIAL
        error_message = str(exc)
        triple_count = len(all_triples)

    final_status = status if error_message is None else status
    async with get_session() as session:
        await KgJobRepo(session).mark_status(
            asset_id,
            final_status,
            error_message=error_message,
            triples_extracted=triple_count,
        )
        await AssetRepo(session).update_kg_status(
            asset_id,
            final_status,
            triple_count=triple_count,
        )

    result = ExtractionResult(
        asset_id=asset_id,
        chunks=chunks,
        triples=all_triples,
        action="extracted" if error_message is None else "partial",
        metadata={"triple_count": triple_count, "error": error_message},
    )
    return {
        "action": result.action,
        "asset_id": str(asset_id),
        "chunks": len(chunks),
        "triples_extracted": triple_count,
        "kg_status": final_status.value,
        "error": error_message,
    }


def extract_kg_for_asset_sync(
    asset_id: uuid.UUID,
    *,
    dry_run: bool = False,
    use_mock: bool = False,
    allow_download: bool = True,
) -> dict:
    return asyncio.run(
        extract_kg_for_asset(
            asset_id,
            dry_run=dry_run,
            use_mock=use_mock,
            allow_download=allow_download,
        )
    )


async def _main_async(args: argparse.Namespace) -> int:
    asset_id = uuid.UUID(args.asset_id)
    summary = await extract_kg_for_asset(
        asset_id,
        dry_run=args.dry_run,
        use_mock=args.mock,
        allow_download=not args.no_download,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("kg_status") != KgStatus.FAILED.value else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract KG triples for one asset")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock extractor")
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
