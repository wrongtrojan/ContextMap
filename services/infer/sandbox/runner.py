"""Subprocess runner for isolated sandbox conda environment."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from services.infer.config import load_infer_config
from services.infer.types import SandboxRequest, SandboxResult


def _sandbox_python(config: dict[str, Any]) -> str:
    sandbox_cfg = config.get("sandbox") or {}
    conda_python = sandbox_cfg.get("conda_python")
    if conda_python:
        return str(conda_python)
    return sys.executable


async def run_sandbox(req: SandboxRequest, *, config: dict[str, Any] | None = None) -> SandboxResult:
    cfg = config or load_infer_config()
    sandbox_cfg = cfg.get("sandbox") or {}
    if not sandbox_cfg.get("enabled", True):
        return SandboxResult(status="error", message="sandbox disabled")

    python_exe = _sandbox_python(cfg)
    timeout = float(sandbox_cfg.get("timeout_sec", 30))
    cmd = [python_exe, "-m", "services.infer.sandbox.worker"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(json.dumps(req.to_dict()).encode("utf-8")),
        timeout=timeout,
    )
    if proc.returncode != 0 and not stdout:
        message = stderr.decode("utf-8", errors="replace") or f"exit code {proc.returncode}"
        return SandboxResult(status="error", message=message)

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return SandboxResult(status="error", message=f"invalid sandbox output: {exc}")

    if payload.get("status") == "success":
        return SandboxResult(status="success", result=payload.get("result"))
    return SandboxResult(status="error", message=str(payload.get("message") or "sandbox failed"))
