"""Tests for run_infer orchestration."""

import pytest

from services.evaluate.types import EvaluationReport, InferHints
from services.infer.infer import run_infer


@pytest.mark.asyncio
async def test_run_infer_skips_when_no_triggers(monkeypatch):
    async def fail_prep(*_args, **_kwargs):
        raise AssertionError("sandbox prep should not run")

    monkeypatch.setattr("services.infer.infer.prepare_sandbox_request", fail_prep)

    results = await run_infer(
        query="hello world",
        evidence=[{"content_unit_id": "1", "content": "text", "metadata": {"type": "text"}}],
        eval_report=EvaluationReport(
            recommendation="proceed",
            confidence=0.9,
            evidence=[],
            scores=[],
            infer_hints=InferHints(need_sandbox=False, visual_candidates=[]),
        ),
        config={"sandbox": {"enabled": True}, "visual": {"enabled": True}, "route": {}},
    )
    assert results == []
