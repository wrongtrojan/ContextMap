"""Tests for infer runtime preflight checks."""

from __future__ import annotations

import sys

import pytest

from services.infer.preflight import check_sandbox_runtime, check_visual_runtime, resolve_sandbox_python


def test_resolve_sandbox_python_prefers_explicit():
    cfg = {"sandbox": {"conda_python": "/opt/custom/python", "conda_env": "infer-sandbox"}}
    assert resolve_sandbox_python(cfg) == "/opt/custom/python"


def test_check_sandbox_runtime_disabled():
    assert check_sandbox_runtime({"sandbox": {"enabled": False}}) is None


def test_check_visual_runtime_disabled():
    assert check_visual_runtime({"visual": {"enabled": False}}) is None


def test_check_visual_runtime_missing_vllm(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "vllm":
            raise ImportError("no vllm")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    err = check_visual_runtime({"visual": {"enabled": True, "preflight": True}})
    assert err is not None
    assert "vllm" in err


def test_check_sandbox_runtime_missing_python(tmp_path):
    missing = tmp_path / "missing-python"
    err = check_sandbox_runtime(
        {
            "sandbox": {
                "enabled": True,
                "preflight": True,
                "conda_python": str(missing),
            }
        }
    )
    assert err is not None
    assert "not found" in err


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("sympy"),
    reason="sympy not installed in current interpreter",
)
def test_check_sandbox_runtime_current_python_ok():
    err = check_sandbox_runtime(
        {
            "sandbox": {
                "enabled": True,
                "preflight": True,
                "conda_python": sys.executable,
            }
        }
    )
    assert err is None
