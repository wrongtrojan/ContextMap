"""Tests for modelscope download helper."""

from pathlib import Path

from services.common import modelscope_download


def test_is_model_ready_detects_config(tmp_path: Path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    assert modelscope_download.is_model_ready(model_dir)


def test_ensure_model_dir_skips_when_ready(tmp_path: Path):
    model_dir = tmp_path / "ready"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    path = modelscope_download.ensure_model_dir(model_dir=model_dir, modelscope_repo="dummy/repo")
    assert path == model_dir
