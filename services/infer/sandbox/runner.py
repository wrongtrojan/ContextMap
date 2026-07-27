"""Subprocess runner for isolated sandbox conda environment."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from paths import PROJECT_ROOT
from services.infer.config import load_infer_config
from services.infer.preflight import check_sandbox_runtime, resolve_sandbox_python
from services.infer.types import SandboxRequest, SandboxResult

_SANDBOX_WORKER_SCRIPT = PROJECT_ROOT / "services/infer/sandbox/worker.py"


async def run_sandbox(req: SandboxRequest, *, config: dict[str, Any] | None = None) -> SandboxResult:
    cfg = config or load_infer_config()
    sandbox_cfg = cfg.get("sandbox") or {}
    if not sandbox_cfg.get("enabled", True):
        return SandboxResult(status="error", message="sandbox disabled")

    preflight_error = check_sandbox_runtime(cfg)
    if preflight_error is not None:
        return SandboxResult(status="error", message=preflight_error)

    python_exe = resolve_sandbox_python(cfg)
    timeout = float(sandbox_cfg.get("timeout_sec", 30))
    # Run worker.py directly — `-m services.infer.sandbox.worker` imports services.infer
    # __init__ (yaml/torch/...) which infer-sandbox env does not have.
    cmd = [python_exe, str(_SANDBOX_WORKER_SCRIPT)]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(req.to_dict()).encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SandboxResult(status="error", message=f"sandbox timed out after {timeout:.0f}s")

    if proc.returncode != 0 and not stdout:
        message = stderr.decode("utf-8", errors="replace") or f"exit code {proc.returncode}"
        return SandboxResult(status="error", message=message.strip())

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        detail = stderr.decode("utf-8", errors="replace").strip()
        suffix = f" ({detail})" if detail else ""
        return SandboxResult(status="error", message=f"invalid sandbox output: {exc}{suffix}")

    if payload.get("status") == "success":
        return SandboxResult(status="success", result=payload.get("result"))
    return SandboxResult(status="error", message=str(payload.get("message") or "sandbox failed"))
