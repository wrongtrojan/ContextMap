"""Tests for core chat graph helpers."""

from core.chats_graph import apply_refetch_hint, merge_evidence, route_after_evaluate, should_refetch
from services.evaluate.types import EvaluationReport, RefetchHint


def test_should_refetch_respects_max_retries():
    report = EvaluationReport(
        recommendation="refetch",
        confidence=0.3,
        evidence=[],
        scores=[],
        refetch_hint=RefetchHint(append_keywords=["heap"]),
    )
    assert should_refetch(report, retry_index=0, max_retries=2) == "refetch"
    assert should_refetch(report, retry_index=2, max_retries=2) == "proceed"


def test_should_refetch_stop_loss_on_retry():
    report = EvaluationReport(
        recommendation="refetch",
        confidence=0.75,
        evidence=[],
        scores=[],
        refetch_hint=RefetchHint(append_keywords=["heap"]),
    )
    assert should_refetch(report, retry_index=1, max_retries=2, stop_loss_confidence=0.6) == "proceed"


def test_apply_refetch_hint_expands_keywords_and_top_k():
    adjusted = apply_refetch_hint(
        {"search_params": {"keywords": ["stack"], "top_k": 8}},
        RefetchHint(top_k_multiplier=1.5, append_keywords=["frame"]),
    )
    assert adjusted["search_params"]["top_k"] == 12
    assert "frame" in adjusted["search_params"]["keywords"]


def test_merge_evidence_deduplicates():
    existing = [{"content_unit_id": "1", "score": 0.5}]
    new_items = [
        {"content_unit_id": "1", "score": 0.9},
        {"content_unit_id": "2", "score": 0.8, "rerank_score": 0.8},
    ]
    merged = merge_evidence(existing, new_items)
    assert len(merged) == 2
    assert merged[0]["content_unit_id"] == "2"


def test_route_after_evaluate_proceed_on_stop_loss():
    state = {
        "retry_index": 1,
        "last_evaluation": {"recommendation": "refetch", "confidence": 0.8},
        "evidence": [],
    }
    assert route_after_evaluate(state) == "expand_media"
