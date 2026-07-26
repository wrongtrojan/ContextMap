"""Tests for sandbox subprocess protocol."""

import json
import sys

import pytest

from services.infer.sandbox.worker import run_calculation
from services.infer.types import SandboxRequest


def test_run_calculation_eval_mode():
    result = run_calculation("2 + 3", mode="eval")
    assert result == 5


@pytest.mark.asyncio
async def test_run_sandbox_protocol(monkeypatch):
    from services.infer.sandbox import runner

    class FakeProc:
        returncode = 0

        async def communicate(self, _stdin):
            return json.dumps({"status": "success", "result": 42}).encode("utf-8"), b""

    captured: dict = {}

    async def fake_create(*cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", fake_create)

    result = await runner.run_sandbox(
        SandboxRequest(expression="1+1", mode="eval"),
        config={"sandbox": {"enabled": True, "timeout_sec": 5, "conda_python": sys.executable}},
    )
    assert result.status == "success"
    assert result.result == 42
    assert captured["cmd"][0] == sys.executable
