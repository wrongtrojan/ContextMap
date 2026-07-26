"""Tests for lazy AutoRE model download layout."""

from __future__ import annotations

from pathlib import Path

import pytest
from safetensors.torch import save_file

from services.kg.autore_runtime import (
    AutoRERuntimeConfig,
    _adapter_dir,
    _discover_adapter_path,
    _is_adapter_ready,
    ensure_autore_models,
)


def test_adapter_dir_layout():
    root = Path("/tmp/autore-test")
    cfg = AutoRERuntimeConfig(model_dir=str(root))
    assert _adapter_dir(root, "head").name == "subject"
    assert _adapter_dir(root, "relation").name == "relation"


def test_ensure_autore_models_no_download_raises(tmp_path: Path):
    cfg = AutoRERuntimeConfig(model_dir=str(tmp_path / "autore"))
    with pytest.raises(RuntimeError, match="HuggingFace"):
        ensure_autore_models(cfg, allow_download=False)


def test_discover_adapter_ready(tmp_path: Path):
    root = tmp_path / "autore"
    subject = root / "subject"
    subject.mkdir(parents=True)
    (subject / "adapter_config.json").write_text("{}", encoding="utf-8")
    save_file({"dummy": __import__("torch").zeros(1)}, subject / "adapter_model.safetensors")
    assert _is_adapter_ready(subject)
    assert _discover_adapter_path(root, "head") == subject
