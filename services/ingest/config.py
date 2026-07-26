"""Ingest configuration loaders (shim aggregating embedding + MinIO)."""

from __future__ import annotations

from typing import Any

from services.ingest.embed import load_embedding_config
from services.ingest.minio_client import load_minio_config


def load_ingest_config() -> dict[str, Any]:
    """Return ingest-related config sections from contextmap.yaml."""
    return {
        "embedding": load_embedding_config(),
        "minio": load_minio_config(),
    }


__all__ = ["load_embedding_config", "load_ingest_config", "load_minio_config"]
