"""Tests for visual expert fail-fast behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.infer.types import VisualRequest
from services.infer.visual import expert as expert_module
from services.infer.visual.infer import run_visual_batch


@pytest.fixture(autouse=True)
def _reset_visual_cache():
    expert_module.reset_visual_expert_cache()
    yield
    expert_module.reset_visual_expert_cache()


def test_visual_batch_preflight_fail_open_without_loading_model(monkeypatch):
    calls = {"describe": 0}

    class FakeExpert:
        def describe(self, **_kwargs):
            calls["describe"] += 1
            return "should not run"

    monkeypatch.setattr(
        "services.infer.visual.infer.check_visual_runtime",
        lambda _cfg: "preflight blocked",
    )
    monkeypatch.setattr(
        "services.infer.visual.infer.get_visual_expert",
        lambda: FakeExpert(),
    )

    requests = [
        VisualRequest(query="q", evidence={"content_unit_id": f"u{i}"}, image_path=f"/tmp/{i}.jpg")
        for i in range(4)
    ]
    results = run_visual_batch(requests, config={"visual": {"enabled": True}}, fail_open=True)
    assert len(results) == 4
    assert all("visual unavailable" in item.content for item in results)
    assert calls["describe"] == 0


def test_visual_expert_reuses_cached_load_failure(tmp_path: Path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    cfg = {"visual": {"enabled": True, "preflight": False, "timeout_sec": 5}}
    visual = expert_module.VisualExpert(model_dir, device="cpu", config=cfg)
    visual._load_error = "load failed once"

    with pytest.raises(RuntimeError, match="load failed once"):
        visual.describe(query="q", image_path=str(tmp_path / "a.jpg"))
    with pytest.raises(RuntimeError, match="load failed once"):
        visual.describe(query="q", image_path=str(tmp_path / "b.jpg"))
