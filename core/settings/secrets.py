"""Read/write local secrets file (DEEPSEEK_API_KEY, etc.)."""

from __future__ import annotations

import os
from pathlib import Path

from paths import LOCAL_SECRETS_ENV, PROJECT_ROOT


def _parse_env_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def read_secrets_file(path: Path | None = None) -> dict[str, str]:
    env_path = path or LOCAL_SECRETS_ENV
    if not env_path.is_file():
        return {}
    return _parse_env_lines(env_path.read_text(encoding="utf-8"))


def load_secrets_into_environ(project_root: Path | None = None) -> None:
    """Load storage/local/secrets.env with setdefault (does not override existing env)."""
    root = project_root or PROJECT_ROOT
    env_path = root / "storage" / "local" / "secrets.env"
    if not env_path.is_file():
        return
    for key, value in _parse_env_lines(env_path.read_text(encoding="utf-8")).items():
        os.environ.setdefault(key, value)


def upsert_secret(key: str, value: str, path: Path | None = None) -> Path:
    """Atomically upsert one secret key into secrets.env."""
    env_path = path or LOCAL_SECRETS_ENV
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_secrets_file(env_path) if env_path.is_file() else {}
    existing[key] = value

    lines = ["# Managed by ContextMap Settings UI — do not commit", ""]
    for k, v in sorted(existing.items()):
        lines.append(f"{k}={v}")
    lines.append("")
    content = "\n".join(lines)

    tmp = env_path.with_suffix(env_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(env_path)
    return env_path


def apply_secret_hot_reload(key: str, value: str) -> None:
    os.environ[key] = value
