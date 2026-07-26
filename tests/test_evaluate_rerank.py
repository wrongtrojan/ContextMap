"""Tests for rerank scoring."""

import pytest

from services.evaluate.rerank import rerank_scores


def _mock_score_fn(query: str, passages: list[str]) -> list[float]:
    del query
    return [1.0 / (index + 1) for index in range(len(passages))]


def test_rerank_scores_ordering():
    scores = rerank_scores("stack frame", ["heap alloc", "stack frame diagram"], score_fn=_mock_score_fn)
    assert scores == [1.0, 0.5]


@pytest.mark.asyncio
async def test_rerank_evidence_sort():
    from services.evaluate.rerank import rerank_evidence

    evidence = [
        {"content_unit_id": "a", "content": "low"},
        {"content_unit_id": "b", "content": "high"},
    ]

    def score_fn(_query, passages):
        return [0.1 if "low" in text else 0.9 for text in passages]

    ranked = await rerank_evidence(query="q", evidence=evidence, score_fn=score_fn)
    assert ranked[0][0]["content_unit_id"] == "b"
