"""Project root, asset paths, and config file location."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONTEXTMAP_CONFIG = PROJECT_ROOT / "configs" / "contextmap.yaml"

ASSETS_DIR = PROJECT_ROOT / "storage" / "assets"
RAW_PDF_DIR = ASSETS_DIR / "raw" / "pdf"
RAW_VIDEO_DIR = ASSETS_DIR / "raw" / "video"
RAW_AUDIO_DIR = ASSETS_DIR / "raw" / "audio"
PROCESSED_PDF_DIR = ASSETS_DIR / "processed" / "pdf"
PROCESSED_VIDEO_DIR = ASSETS_DIR / "processed" / "video"
PROCESSED_AUDIO_DIR = ASSETS_DIR / "processed" / "audio"


def modality_dirs() -> dict[str, Path]:
    return {
        "pdf": PROCESSED_PDF_DIR,
        "video": PROCESSED_VIDEO_DIR,
        "audio": PROCESSED_AUDIO_DIR,
    }
