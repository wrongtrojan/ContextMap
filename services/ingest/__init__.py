"""Ingest pipeline: load processed assets into Postgres."""

from services.ingest.config import load_ingest_config
from services.ingest.ingest_assets import ingest_processed_dir

__all__ = [
    "ingest_processed_dir",
    "load_ingest_config",
]
