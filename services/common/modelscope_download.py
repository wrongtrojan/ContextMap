"""ModelScope model download helpers (HuggingFace-free path)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROJECT_ROOT

MODEL_MARKERS = ("config.json", "modules.json", "model.safetensors", "pytorch_model.bin")


def is_model_ready(model_dir: Path) -> bool:
    if not model_dir.exists():
        return False
    names = {path.name for path in model_dir.rglob("*") if path.is_file()}
    return any(marker in names for marker in MODEL_MARKERS)


def ensure_model_dir(*, model_dir: Path, modelscope_repo: str) -> Path:
    """Download from ModelScope when local weights are missing."""
    resolved = model_dir if model_dir.is_absolute() else PROJECT_ROOT / model_dir
    if is_model_ready(resolved):
        return resolved

    resolved.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "modelscope is required to download models. Install with: pip install modelscope"
        ) from exc

    snapshot_download(modelscope_repo, local_dir=str(resolved))
    return resolved


def _resolve_config_section(section: str, config_path: Path) -> tuple[Path, str]:
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    parts = section.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"Config section not found: {section}")
        node = node[part]

    if not isinstance(node, dict):
        raise KeyError(f"Config section must be a mapping: {section}")

    model_dir = node.get("model_dir")
    modelscope_repo = node.get("modelscope_repo")
    if not model_dir or not modelscope_repo:
        raise KeyError(f"Section {section} requires model_dir and modelscope_repo")

    return PROJECT_ROOT / str(model_dir), str(modelscope_repo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a model section via ModelScope")
    parser.add_argument(
        "--section",
        required=True,
        help="YAML section path, e.g. evaluate.reranker or infer.visual",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONTEXTMAP_CONFIG,
        help="Path to contextmap.yaml",
    )
    args = parser.parse_args()
    model_dir, repo = _resolve_config_section(args.section, args.config)
    path = ensure_model_dir(model_dir=model_dir, modelscope_repo=repo)
    print(f"Model ready at {path}")


if __name__ == "__main__":
    main()
