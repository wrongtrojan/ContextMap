"""Live-corpus retrieval evaluation: recall + precision for hybrid/keyword/vector."""

from __future__ import annotations

import pytest

from services.retrieval.config import load_retrieval_config
from tests.helpers.retrieval_eval import (
    DEFAULT_TOP_K,
    corpus_available,
    eval_all_modes,
    eval_in_corpus,
    eval_mode,
    eval_nl_queries,
    format_report,
    keyword_only_config,
)


@pytest.fixture
async def corpus_ready():
    ok, reason = await corpus_available()
    if not ok:
        pytest.skip(reason)


@pytest.fixture
def retrieval_config() -> dict:
    return load_retrieval_config()


@pytest.mark.asyncio
async def test_hybrid_in_corpus_metrics(corpus_ready, retrieval_config):
    report = await eval_in_corpus(retrieval_config, top_k=DEFAULT_TOP_K)
    assert report.queries >= 20, f"too few in-corpus cases: {report.queries}"
    assert report.recall_at_k >= 0.80, format_report(report)
    assert report.precision_at_k >= 0.15, format_report(report)
    assert report.mrr >= 0.70, format_report(report)


@pytest.mark.asyncio
async def test_hybrid_nl_metrics(corpus_ready, retrieval_config):
    report = await eval_nl_queries(retrieval_config, top_k=DEFAULT_TOP_K)
    assert report.recall_at_k >= 0.48, format_report(report)
    assert report.precision_at_k >= 0.30, format_report(report)


@pytest.mark.asyncio
async def test_hybrid_beats_or_matches_keyword_combined(corpus_ready, retrieval_config):
    hybrid = await eval_mode(retrieval_config, mode="hybrid", top_k=DEFAULT_TOP_K)
    keyword = await eval_mode(keyword_only_config(retrieval_config), mode="keyword_only", top_k=DEFAULT_TOP_K)

    h = hybrid.combined
    k = keyword.combined
    assert h.recall_at_k >= k.recall_at_k, (
        f"recall hybrid={h.recall_at_k:.0%} keyword={k.recall_at_k:.0%}"
    )
    assert h.f1_at_k >= k.f1_at_k * 0.95, (
        f"f1 hybrid={h.f1_at_k:.0%} keyword={k.f1_at_k:.0%}"
    )


@pytest.mark.asyncio
async def test_vector_nl_recall_improves_with_semantic_query(corpus_ready, retrieval_config):
    from tests.helpers.retrieval_eval import vector_only_config

    report = await eval_nl_queries(vector_only_config(retrieval_config), top_k=DEFAULT_TOP_K)
    assert report.recall_at_k >= 0.35, format_report(report)


@pytest.mark.asyncio
async def test_eval_report_all_modes(corpus_ready, retrieval_config):
    """Printable comparison table; guards against large regressions on any metric."""
    reports = await eval_all_modes(retrieval_config, top_k=DEFAULT_TOP_K)
    by_mode = {item.mode: item for item in reports}

    hybrid = by_mode["hybrid"].combined
    keyword = by_mode["keyword_only"].combined

    assert hybrid.recall_at_k >= 0.70
    assert hybrid.precision_at_k >= 0.10
    assert hybrid.recall_at_k >= keyword.recall_at_k

    lines = [f"Retrieval eval @k={DEFAULT_TOP_K} (combined in-corpus + NL):"]
    for item in reports:
        combined = item.combined
        lines.append(
            f"  {item.mode:13} {format_report(combined)} | "
            f"in-corpus {format_report(item.in_corpus)} | nl {format_report(item.nl_queries)}"
        )
    print("\n".join(lines))
