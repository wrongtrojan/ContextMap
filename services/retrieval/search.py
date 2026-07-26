"""Hybrid search orchestrator."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.retrieval.channels.graph import graph_channel
from services.retrieval.channels.keyword import keyword_channel
from services.retrieval.channels.vector import vector_channel
from services.retrieval.config import load_retrieval_config
from services.retrieval.dedup import deduplicate_and_rank
from services.retrieval.format import format_results
from services.retrieval.fusion import fuse_channel_hits
from services.retrieval.prepare import parse_search_needs, refine_query
from services.retrieval.resolve import resolve_preferences
from services.retrieval.types import HybridSearchDebug, RetrievalQuery


async def _run_graph_channel(session, query, config):
    return await graph_channel(session, query, config=config)


async def hybrid_search(
    session: AsyncSession,
    *,
    search_needs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_retrieval_config()
    query = parse_search_needs(search_needs)
    if not query.top_k:
        query.top_k = int(cfg.get("top_k_default", 8))

    debug = HybridSearchDebug()
    t0 = time.perf_counter()

    query = await resolve_preferences(session, query)
    debug.timings_ms["resolve"] = (time.perf_counter() - t0) * 1000

    t_channels = time.perf_counter()
    vector_result, keyword_result, graph_result = await asyncio.gather(
        vector_channel(session, query, config=cfg),
        keyword_channel(session, query, config=cfg),
        _run_graph_channel(session, query, cfg),
        return_exceptions=True,
    )

    if isinstance(vector_result, Exception):
        return {"status": "error", "message": f"vector channel failed: {vector_result}"}
    if isinstance(keyword_result, Exception):
        return {"status": "error", "message": f"keyword channel failed: {keyword_result}"}

    graph_hits: list = []
    if isinstance(graph_result, Exception):
        debug.graph_error = str(graph_result)
        graph_skip_reason = None
    else:
        graph_hits, graph_skip_reason, graph_error = graph_result
        debug.graph_skipped = graph_skip_reason is not None
        debug.graph_skip_reason = graph_skip_reason
        debug.graph_error = graph_error

    debug.timings_ms["channels"] = (time.perf_counter() - t_channels) * 1000
    debug.channel_counts = {
        "vector": len(vector_result),
        "keyword": len(keyword_result),
        "graph": len(graph_hits),
    }

    channel_hits = {
        "vector": vector_result,
        "keyword": keyword_result,
        "graph": graph_hits,
    }

    t_fuse = time.perf_counter()
    fused = fuse_channel_hits(channel_hits, query, config=cfg)
    debug.timings_ms["fusion"] = (time.perf_counter() - t_fuse) * 1000

    t_dedup = time.perf_counter()
    final_hits, dedup_stats = deduplicate_and_rank(fused, top_k=query.top_k, config=cfg)
    debug.dedup_removed = dedup_stats
    debug.timings_ms["dedup"] = (time.perf_counter() - t_dedup) * 1000

    results = format_results(final_hits)
    debug.timings_ms["total"] = (time.perf_counter() - t0) * 1000

    return {
        "status": "success",
        "results": results,
        "debug": debug.model_dump(),
    }


async def search_from_context(
    session: AsyncSession,
    *,
    user_context: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    search_needs = await refine_query(user_context)
    params = search_needs.setdefault("search_params", {})
    if not params.get("semantic_query"):
        params["semantic_query"] = user_context.strip()
    return await hybrid_search(session, search_needs=search_needs, config=config)
