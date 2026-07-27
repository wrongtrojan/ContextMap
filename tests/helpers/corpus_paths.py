"""Shared corpus sample paths for integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from paths import PROJECT_ROOT

AUTORE_DIR = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
)
AUTORE_MIDDLE = AUTORE_DIR / (
    "Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models_middle.json"
)
AUTORE_IMAGES = AUTORE_DIR / "images"

PROCESSED_AUDIO_ROOT = PROJECT_ROOT / "storage/assets/processed/audio"


def find_audio_processed_dir() -> Path | None:
    if not PROCESSED_AUDIO_ROOT.is_dir():
        return None
    for path in sorted(PROCESSED_AUDIO_ROOT.iterdir()):
        if not path.is_dir() or not (path / "meta.json").is_file():
            continue
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        if meta.get("status") == "success" and meta.get("modality") == "audio":
            return path
    return None
