"""Smoke tests for unified contextmap.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from database.config import load_postgres_config
from paths import CONTEXTMAP_CONFIG, PROCESSED_PDF_DIR, RAW_PDF_DIR
from services.ingest.embed import load_embedding_config
from services.outline.llm import load_outline_config
from services.parse.parse_pdf import mineru_defaults

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_contextmap_yaml_has_required_sections() -> None:
    assert CONTEXTMAP_CONFIG.is_file()
    with CONTEXTMAP_CONFIG.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    for key in ("postgres", "minio", "embedding", "parse", "whisper", "outline"):
        assert key in data
    assert "assets" not in data
    assert "paths" not in data


def test_section_loaders_read_contextmap() -> None:
    postgres = load_postgres_config()
    assert postgres["database"] == "contextmap"
    embedding = load_embedding_config()
    assert embedding["dim"] == 1024
    outline = load_outline_config()
    assert "llm" in outline
    mineru = mineru_defaults()
    assert mineru["lang"] == "ch"


def test_paths_are_code_constants() -> None:
    assert RAW_PDF_DIR == PROJECT_ROOT / "storage/assets/raw/pdf"
    assert PROCESSED_PDF_DIR == PROJECT_ROOT / "storage/assets/processed/pdf"
