"""Load PostgreSQL connection settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG

CONFIG_PATH = CONTEXTMAP_CONFIG


def load_postgres_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    cfg = dict(data.get("postgres") or {})
    env_password = os.getenv("POSTGRES_PASSWORD")
    if env_password:
        cfg["password"] = env_password
    return cfg


def build_database_url(config: dict[str, Any] | None = None, *, async_driver: bool = True) -> str:
    cfg = config or load_postgres_config()
    user = cfg["user"]
    password = cfg["password"]
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    database = cfg["database"]
    driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg"
    return f"{driver}://{user}:{password}@{host}:{port}/{database}"
