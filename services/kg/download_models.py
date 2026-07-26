"""
Pre-download AutoRE models (optional — extract also auto-downloads on first run).

- Mistral base: ModelScope (魔搭)
- LoRA adapters: HuggingFace (dante123/AutoRE)

Usage:
  python -m services.kg.download_models
  python -m services.kg.download_models --adapters-only
  python -m services.kg.download_models --base-only
  python -m services.kg.download_models --status
"""

from __future__ import annotations

import argparse
import json
import logging

from services.kg.autore_runtime import (
    _download_adapters,
    _download_base,
    _model_root,
    config_from_yaml,
    ensure_autore_models,
    model_status,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download AutoRE models to models/autore/")
    parser.add_argument("--status", action="store_true", help="Print readiness only")
    parser.add_argument(
        "--adapters-only",
        action="store_true",
        help="Only download LoRA adapters from HuggingFace",
    )
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Only download Mistral base from ModelScope (~14GB)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.adapters_only and args.base_only:
        parser.error("--adapters-only and --base-only are mutually exclusive")

    cfg = config_from_yaml()
    if args.status:
        print(json.dumps(model_status(cfg), indent=2, ensure_ascii=False))
        return

    root = _model_root(cfg)
    root.mkdir(parents=True, exist_ok=True)

    if args.adapters_only:
        print(f"[下载] 仅从 HuggingFace 下载 LoRA 适配器到 {root} ...")
        _download_adapters(root, cfg)
    elif args.base_only:
        print(f"[下载] 仅从魔搭下载 Mistral 基座到 {root} ...")
        _download_base(root, cfg)
    else:
        ensure_autore_models(cfg, allow_download=True)

    status = model_status(cfg)
    print(json.dumps(status, indent=2, ensure_ascii=False))
    if status["ready"]:
        print("AutoRE 模型已全部就绪。")


if __name__ == "__main__":
    main()
