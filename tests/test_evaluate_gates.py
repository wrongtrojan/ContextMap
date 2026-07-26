"""Tests for evaluate recommendation gates."""

from services.evaluate.gates import build_recommendation, should_run_audit


def test_proceed_when_scores_high():
    recommendation, confidence, hint = build_recommendation(
        max_rerank=0.8,
        coverage=0.9,
        thresholds={"proceed_rerank": 0.55, "min_coverage": 0.6},
        missing_facets=[],
    )
    assert recommendation == "proceed"
    assert hint is None
    assert confidence > 0.5


def test_refetch_when_low_rerank():
    recommendation, _confidence, hint = build_recommendation(
        max_rerank=0.2,
        coverage=0.9,
        thresholds={"proceed_rerank": 0.55, "min_coverage": 0.6},
        missing_facets=["heap"],
    )
    assert recommendation == "refetch"
    assert hint is not None
    assert "heap" in hint.append_keywords


def test_audit_borderline_trigger():
    assert should_run_audit(
        max_rerank=0.5,
        coverage=0.8,
        thresholds={"audit_on_borderline": True, "borderline_low": 0.4, "borderline_high": 0.55, "min_coverage": 0.6},
    )
