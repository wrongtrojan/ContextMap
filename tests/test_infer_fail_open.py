"""Tests for run_infer fail-open orchestration."""

import pytest

from services.evaluate.types import EvaluationReport, InferHints
from services.infer.infer import run_infer
from services.infer.types import InferTrigger, VisualRequest


@pytest.mark.asyncio
async def test_run_infer_visual_fail_open(monkeypatch):
    evidence = [
        {
            "content_unit_id": "v1",
            "content": "diagram",
            "rerank_score": 0.8,
            "metadata": {"type": "frame", "has_visual_asset": True, "image_filename": "a.jpg"},
        }
    ]
    report = EvaluationReport(
        recommendation="proceed",
        confidence=0.9,
        evidence=evidence,
        scores=[],
        infer_hints=InferHints(visual_candidates=evidence),
    )

    monkeypatch.setattr(
        "services.infer.infer.route_infer",
        lambda **_kwargs: InferTrigger(
            run_visual=True,
            visual_requests=[VisualRequest(query="q", evidence=evidence[0], image_path="/tmp/a.jpg")],
        ),
    )

    results = await run_infer(
        query="explain diagram",
        evidence=evidence,
        eval_report=report,
        config={"fail_open": True, "visual": {"enabled": True, "preflight": True}},
    )
    assert len(results) == 1
    assert results[0].kind == "visual"
    assert "visual unavailable" in results[0].content or "visual inference failed" in results[0].content


@pytest.mark.asyncio
async def test_run_infer_sandbox_fail_open_skips_prep(monkeypatch):
    called = {"prep": False}

    async def fake_prep(*_args, **_kwargs):
        called["prep"] = True
        from services.infer.types import SandboxRequest

        return SandboxRequest(expression="1+1", mode="eval")

    monkeypatch.setattr("services.infer.infer.prepare_sandbox_request", fake_prep)
    monkeypatch.setattr(
        "services.infer.infer.route_infer",
        lambda **_kwargs: InferTrigger(run_sandbox=True, run_visual=False),
    )
    monkeypatch.setattr(
        "services.infer.infer.check_sandbox_runtime",
        lambda _cfg: "sandbox env missing",
    )

    results = await run_infer(
        query="计算 1+1",
        evidence=[],
        config={"fail_open": True},
    )
    assert called["prep"] is False
    assert len(results) == 1
    assert results[0].kind == "sandbox"
    assert "sandbox unavailable" in results[0].content
