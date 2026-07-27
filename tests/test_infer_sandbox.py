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
    monkeypatch.setattr(runner, "check_sandbox_runtime", lambda _cfg: None)

    result = await runner.run_sandbox(
        SandboxRequest(expression="1+1", mode="eval"),
        config={"sandbox": {"enabled": True, "timeout_sec": 5, "conda_python": sys.executable}},
    )
    assert result.status == "success"
    assert result.result == 42
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1].endswith("services/infer/sandbox/worker.py")


@pytest.mark.asyncio
@pytest.mark.skipif(
    __import__("importlib").util.find_spec("sympy") is None,
    reason="sympy not installed",
)
async def test_run_sandbox_real_subprocess():
    from services.infer.sandbox import runner

    result = await runner.run_sandbox(
        SandboxRequest(expression="2 + 3", mode="eval"),
        config={
            "sandbox": {
                "enabled": True,
                "preflight": True,
                "timeout_sec": 10,
                "conda_python": sys.executable,
            }
        },
    )
    assert result.status == "success"
    assert result.result == 5


@pytest.mark.asyncio
async def test_run_sandbox_infer_sandbox_conda_env():
    """Real subprocess via isolated infer-sandbox conda (numpy+sympy only)."""
    from services.infer.preflight import resolve_sandbox_python
    from services.infer.sandbox import runner

    cfg = {"sandbox": {"enabled": True, "preflight": True, "timeout_sec": 15, "conda_env": "infer-sandbox"}}
    python_exe = resolve_sandbox_python(cfg)
    if "infer-sandbox" not in python_exe:
        pytest.skip("infer-sandbox conda env not available")

    result = await runner.run_sandbox(
        SandboxRequest(expression="2 * 21", mode="eval"),
        config=cfg,
    )
    assert result.status == "success", result.message
    assert result.result == 42
