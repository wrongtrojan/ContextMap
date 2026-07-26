"""Acceptance checks for ingest + pgvector retrieval."""

from __future__ import annotations

import asyncio

from database.repositories import ContentUnitRepo
from database.session import dispose_engine, get_session
from services.ingest.embed import embed_texts


async def main() -> None:
    query = "document-level relation extraction with large language models"
    query_vec = embed_texts([query])[0]

    async with get_session() as session:
        repo = ContentUnitRepo(session)
        hits = await repo.vector_search(query_vec, limit=5)

    print(f"Query: {query}")
    print(f"Hits: {len(hits)}")
    for index, hit in enumerate(hits, 1):
        preview = hit.unit.search_text[:120].replace("\n", " ")
        print(f"{index}. score={hit.score:.4f} type={hit.unit.content_type.value} text={preview}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
