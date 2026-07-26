"""Tests for evaluate_evidence orchestration."""

import pytest

from services.evaluate.evaluate import evaluate_evidence


@pytest.mark.asyncio
async def test_evaluate_evidence_proceed_with_mock_reranker():
    evidence = [
        {"content_unit_id": "1", "content": "stack frame activation record", "score": 0.9, "metadata": {"type": "text"}},
        {"content_unit_id": "2", "content": "unrelated heap allocator", "score": 0.2, "metadata": {"type": "text"}},
    ]
    search_needs = {
        "search_params": {
            "keywords": ["stack", "frame"],
            "semantic_query": "stack frame layout",
            "top_k": 8,
        }
    }

    def score_fn(_query, passages):
        return [0.9 if "stack" in text else 0.1 for text in passages]

    report = await evaluate_evidence(
        user_query="explain stack frame",
        search_needs=search_needs,
        evidence=evidence,
        score_fn=score_fn,
        run_llm_audit=False,
        config={
            "thresholds": {
                "proceed_rerank": 0.55,
                "min_coverage": 0.5,
                "min_keep_score": 0.35,
                "audit_on_borderline": False,
            },
            "keep_top_k": 8,
        },
    )
    assert report.recommendation == "proceed"
    assert report.evidence
    assert report.evidence[0]["content_unit_id"] == "1"
    assert report.scores[0].rerank_score >= 0.9
