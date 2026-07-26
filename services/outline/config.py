"""Load outline settings from configs/contextmap.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG

# Re-export from llm.py for unified config access; llm.py remains the implementation home.
from services.outline.llm import load_outline_config

__all__ = ["load_outline_config"]
