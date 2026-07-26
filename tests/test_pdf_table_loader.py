"""Unit tests for PDF table/chart/abstract ingest loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.enums import ContentType
from services.ingest.loaders.html_utils import html_table_to_text
from services.ingest.loaders.pdf_units import load_pdf_units

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_DIR = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
)
AUTORE_MIDDLE = AUTORE_DIR / (
    "Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models_middle.json"
)
AUTORE_IMAGES = AUTORE_DIR / "images"


@pytest.mark.skipif(not AUTORE_MIDDLE.exists(), reason="AutoRE sample not present")
def test_autore_loader_counts_and_dedup() -> None:
    units, stats = load_pdf_units(AUTORE_MIDDLE, AUTORE_IMAGES)

    table_units = [u for u in units if u.content_type == ContentType.TABLE]
    text_units = [u for u in units if u.content_type == ContentType.TEXT]
    image_units = [u for u in units if u.content_type == ContentType.IMAGE]

    assert len(table_units) == 7
    assert len(text_units) == 90
    assert len(image_units) == 4

    unique_text = {u.search_text for u in text_units}
    assert len(unique_text) == len(text_units)

    assert stats.block_types_seen.get("table") == 7
    assert stats.block_types_seen.get("chart") == 2
    assert stats.block_types_seen.get("abstract") == 1
    assert len(stats.referenced_images) == 10
    assert stats.disk_images == 11


def test_html_table_to_text_flattens_rows() -> None:
    html = """
    <table>
      <tr><td>Model</td><td>F1</td></tr>
      <tr><td>AutoRE-Vicuna-7B</td><td>0.72</td></tr>
    </table>
    """
    text = html_table_to_text(html)
    assert "Model | F1" in text
    assert "AutoRE-Vicuna-7B | 0.72" in text


@pytest.mark.skipif(not AUTORE_MIDDLE.exists(), reason="AutoRE sample not present")
def test_table_unit_contains_model_name() -> None:
    units, _ = load_pdf_units(AUTORE_MIDDLE, AUTORE_IMAGES)
    table_texts = " ".join(u.search_text for u in units if u.content_type == ContentType.TABLE)
    assert "AutoRE-Vicuna-7B" in table_texts
