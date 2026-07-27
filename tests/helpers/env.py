"""Load .env for live integration tests (read-only)."""

from __future__ import annotations

import os
from pathlib import Path

from core.env import load_dotenv as _load_dotenv, load_secrets as _load_secrets
from paths import PROJECT_ROOT


def load_dotenv(project_root: Path | None = None) -> None:
    root = project_root or PROJECT_ROOT
    _load_secrets(root)
    _load_dotenv(root)


def deepseek_api_key_available(project_root: Path | None = None) -> bool:
    load_dotenv(project_root)
    return bool(os.getenv("DEEPSEEK_API_KEY"))
