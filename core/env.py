"""Load project secrets and .env into os.environ (setdefault, does not override existing)."""

from __future__ import annotations

import os
from pathlib import Path

from paths import LOCAL_SECRETS_ENV, PROJECT_ROOT


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_secrets(project_root: Path | None = None) -> None:
    """Load storage/local/secrets.env before .env (both use setdefault)."""
    root = project_root or PROJECT_ROOT
    secrets_path = root / "storage" / "local" / "secrets.env"
    for key, value in _parse_env_file(secrets_path).items():
        os.environ.setdefault(key, value)


def load_dotenv(project_root: Path | None = None) -> None:
    root = project_root or PROJECT_ROOT
    env_path = root / ".env"
    for key, value in _parse_env_file(env_path).items():
        os.environ.setdefault(key, value)


def llm_api_key_configured(env_name: str = "DEEPSEEK_API_KEY") -> bool:
    return bool(os.getenv(env_name, "").strip())


def secret_hint(env_name: str = "DEEPSEEK_API_KEY") -> str | None:
    value = os.getenv(env_name, "").strip()
    if not value:
        return None
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"
