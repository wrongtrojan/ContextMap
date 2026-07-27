"""Verify shared corpus embeddings were not corrupted by tests."""

from __future__ import annotations

import asyncio
import sys

import numpy as np
from sqlalchemy import select

from database.enums import AssetModality
from database.models import ContentUnit, Asset
from database.session import dispose_engine, get_session
from paths import PROJECT_ROOT
from services.ingest.embed import embed_texts
from tests.helpers.corpus_paths import AUTORE_DIR


async def assert_autore_embeddings_healthy(*, min_sim: float = 0.95) -> None:
    if not AUTORE_DIR.is_dir():
        return

    async with get_session() as session:
        rows = (
            await session.execute(
                select(ContentUnit)
                .join(Asset)
                .where(
                    Asset.modality == AssetModality.PDF,
                    Asset.name.ilike("%AutoRE%"),
                    ContentUnit.embedding.is_not(None),
                )
                .limit(10)
            )
        ).scalars().all()

    if not rows:
        raise RuntimeError(
            "No AutoRE PDF units with embeddings found; run ingest on the AutoRE sample first."
        )

    sims: list[float] = []
    for unit in rows:
        text = (unit.search_text or "")[:512]
        if not text.strip():
            continue
        live = embed_texts([text])[0]
        sim = float(np.dot(np.array(live), np.array(unit.embedding)))
        sims.append(sim)

    if not sims:
        raise RuntimeError("AutoRE sample units have no searchable text for embedding check.")

    mean_sim = float(np.mean(sims))
    if mean_sim < min_sim:
        raise RuntimeError(
            f"AutoRE corpus embeddings unhealthy: mean_sim={mean_sim:.3f} (need >={min_sim}). "
            "Likely test pollution — reingest AutoRE with: "
            "python -m services.ingest.ingest_assets --processed-dir "
            f"'{AUTORE_DIR.relative_to(PROJECT_ROOT)}' --force --skip-minio"
        )


async def _main() -> None:
    try:
        await assert_autore_embeddings_healthy()
        print("corpus_guard: AutoRE embeddings healthy")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
    sys.exit(0)
