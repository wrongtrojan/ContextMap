"""Detect GPU and align device flags in configs/contextmap.yaml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROJECT_ROOT


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def _recommended(data: dict[str, Any], *, has_cuda: bool) -> dict[str, Any]:
    visual_enabled = bool((data.get("infer") or {}).get("visual", {}).get("enabled", True))
    kg_enabled = bool((data.get("kg") or {}).get("enabled", False))

    rec: dict[str, Any] = {
        "embedding.device": "cuda" if has_cuda else "cpu",
        "evaluate.reranker.device": "cuda" if has_cuda else "cpu",
        "infer.visual.device": "cuda" if has_cuda else "cpu",
        "infer.visual.enabled": visual_enabled and has_cuda,
        "kg.autore.device": "cuda" if has_cuda else "cpu",
    }
    if not has_cuda:
        rec["notes"] = (
            "No CUDA detected — visual infer disabled; embedding/reranker set to CPU. "
            "Chat and API LLM features still work via DeepSeek."
        )
    elif not visual_enabled:
        rec["notes"] = "CUDA available; infer.visual.enabled is false in yaml (unchanged unless --apply)."
    elif kg_enabled and not has_cuda:
        rec["notes"] = "kg.enabled is true but CUDA is unavailable — KG will be very slow on CPU."
    else:
        rec["notes"] = "CUDA available — GPU paths enabled where configured."
    return rec


def _nested_set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise KeyError(f"Cannot set {dotted}: {part} is not a mapping")
        node = child
    node[parts[-1]] = value


def calibrate_report(*, config_path: Path = CONTEXTMAP_CONFIG) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    has_cuda = _cuda_available()
    rec = _recommended(data, has_cuda=has_cuda)
    return {
        "config_path": str(config_path),
        "cuda_available": has_cuda,
        "recommendations": {k: v for k, v in rec.items() if k != "notes"},
        "notes": rec.get("notes", ""),
    }


def print_calibrate_report(report: dict[str, Any]) -> None:
    cuda = "yes" if report["cuda_available"] else "no"
    print(f"Calibrator ({report['config_path']})")
    print(f"  CUDA available: {cuda}")
    print("  Recommended settings:")
    for key, value in report["recommendations"].items():
        print(f"    {key}: {value}")
    if report.get("notes"):
        print(f"  Note: {report['notes']}")


def apply_calibration(*, config_path: Path = CONTEXTMAP_CONFIG) -> Path:
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    rec = _recommended(data, has_cuda=_cuda_available())
    for key, value in rec.items():
        if key == "notes":
            continue
        _nested_set(data, key, value)

    tmp = config_path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(config_path)
    return config_path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Calibrate ContextMap device settings")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONTEXTMAP_CONFIG,
        help="Path to contextmap.yaml",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write recommended device flags to contextmap.yaml",
    )
    args = parser.parse_args(argv)

    if args.apply:
        path = apply_calibration(config_path=args.config)
        print(f"Updated {path}")
        print_calibrate_report(calibrate_report(config_path=args.config))
        return 0

    print_calibrate_report(calibrate_report(config_path=args.config))
    print("\nRun with --apply to write these values to contextmap.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
