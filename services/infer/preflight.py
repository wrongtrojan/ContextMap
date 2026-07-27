"""Runtime checks for optional infer subsystems (sandbox, visual)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from paths import PROJECT_ROOT


def _sandbox_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("sandbox") or {})


def _visual_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("visual") or {})


def _python_has_sandbox_deps(python_exe: str) -> bool:
    try:
        proc = subprocess.run(
            [python_exe, "-c", "import numpy, sympy"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _conda_env_python(env_name: str) -> Path | None:
    candidates: list[Path] = []
    conda_exe = shutil.which("conda")
    if conda_exe:
        conda_root = Path(conda_exe).resolve().parent.parent
        candidates.append(conda_root / "envs" / env_name / "bin" / "python")

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(Path(conda_prefix).parent / env_name / "bin" / "python")

    for root_name in ("miniconda3", "anaconda3", "mambaforge", "miniforge3"):
        candidates.append(Path.home() / root_name / "envs" / env_name / "bin" / "python")

    candidates.append(PROJECT_ROOT / ".conda" / "envs" / env_name / "bin" / "python")

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve_sandbox_python(config: dict[str, Any]) -> str:
    """Pick the Python executable for the isolated sandbox worker."""
    sandbox_cfg = _sandbox_cfg(config)
    explicit = sandbox_cfg.get("conda_python")
    if explicit:
        return str(explicit)

    env_name = str(sandbox_cfg.get("conda_env") or "infer-sandbox")
    env_python = _conda_env_python(env_name)
    if env_python is not None and _python_has_sandbox_deps(str(env_python)):
        return str(env_python)

    if _python_has_sandbox_deps(sys.executable):
        return sys.executable

    if env_python is not None:
        return str(env_python)
    return sys.executable


def check_sandbox_runtime(config: dict[str, Any]) -> str | None:
    sandbox_cfg = _sandbox_cfg(config)
    if not sandbox_cfg.get("enabled", True):
        return None
    if not sandbox_cfg.get("preflight", True):
        return None

    python_exe = resolve_sandbox_python(config)
    if not Path(python_exe).is_file():
        return (
            f"sandbox python not found: {python_exe}. "
            f"Create env from environment/infer-sandbox.yaml or set infer.sandbox.conda_python."
        )

    try:
        proc = subprocess.run(
            [python_exe, "-c", "import numpy, sympy"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"sandbox env check failed for {python_exe}: {exc}"

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        return (
            f"sandbox env missing numpy/sympy ({python_exe}). "
            f"Run: conda env create -f environment/infer-sandbox.yaml. {stderr}"
        )
    return None


def check_visual_runtime(config: dict[str, Any]) -> str | None:
    visual_cfg = _visual_cfg(config)
    if not visual_cfg.get("enabled", True):
        return None
    if not visual_cfg.get("preflight", True):
        return None

    try:
        import vllm  # noqa: F401
    except ImportError:
        return (
            "vllm is not installed. Install optional visual deps: "
            "pip install -r environment/requirements.txt"
        )

    enforce_eager = bool(visual_cfg.get("enforce_eager", True))
    if not enforce_eager and shutil.which("ninja") is None:
        return (
            "ninja is not installed (required for vLLM flashinfer JIT). "
            "Install ninja or set infer.visual.enforce_eager: true"
        )

    device = str(visual_cfg.get("device") or "cuda")
    if device.startswith("cuda"):
        try:
            import torch

            if not torch.cuda.is_available():
                return "CUDA is not available for visual inference"
        except ImportError:
            return "torch is not installed for visual inference"

    try:
        import qwen_vl_utils  # noqa: F401
    except ImportError:
        return (
            "qwen-vl-utils is not installed. Install optional visual deps: "
            "pip install -r environment/requirements.txt"
        )

    return None
