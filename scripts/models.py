"""Pre-download ModelScope / AutoRE weights before first run."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROJECT_ROOT
from scripts.model_catalog import DEFAULT_CONFIG, MODEL_SPECS, PROFILES, ModelSpec
from services.common.modelscope_download import ensure_model_dir, is_model_ready
from services.parse.whisper_runtime import is_whisper_model_ready, whisper_model_dir, WhisperRuntimeConfig


def _load_yaml(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _config_section(data: dict[str, Any], section: str) -> dict[str, Any]:
    node: Any = data
    for part in section.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"Config section not found: {section}")
        node = node[part]
    if not isinstance(node, dict):
        raise KeyError(f"Config section must be a mapping: {section}")
    return node


def _resolve_modelscope(spec: ModelSpec, config_path: Path) -> tuple[Path, str]:
    data = _load_yaml(config_path)
    node = _config_section(data, spec.section)
    model_dir = node.get("model_dir")
    modelscope_repo = node.get("modelscope_repo")
    if not model_dir or not modelscope_repo:
        raise KeyError(f"{spec.section} requires model_dir and modelscope_repo")
    resolved = Path(model_dir)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved, str(modelscope_repo)


def _whisper_paths(config_path: Path) -> tuple[Path, str]:
    data = _load_yaml(config_path)
    node = _config_section(data, "whisper")
    cfg = WhisperRuntimeConfig(
        model_dir=str(node.get("model_dir", "models/whisper_v3")),
        modelscope_repo=str(node.get("modelscope_repo", "Systran/faster-whisper-large-v3")),
    )
    return whisper_model_dir(cfg), cfg.modelscope_repo


def is_spec_ready(spec: ModelSpec, config_path: Path = DEFAULT_CONFIG) -> bool:
    if spec.kind == "autore":
        from services.kg.autore_runtime import model_status

        return bool(model_status().get("ready"))

    if spec.key == "whisper":
        model_dir, _ = _whisper_paths(config_path)
        return is_whisper_model_ready(model_dir)

    model_dir, _ = _resolve_modelscope(spec, config_path)
    return is_model_ready(model_dir)


def spec_status(spec: ModelSpec, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    ready = is_spec_ready(spec, config_path)
    if spec.kind == "autore":
        from services.kg.autore_runtime import model_status

        detail = model_status()
        return {
            "key": spec.key,
            "label": spec.label,
            "ready": ready,
            "path": detail.get("root"),
            "size_hint": spec.size_hint,
            "detail": detail,
        }

    if spec.key == "whisper":
        model_dir, repo = _whisper_paths(config_path)
        return {
            "key": spec.key,
            "label": spec.label,
            "ready": ready,
            "path": str(model_dir),
            "repo": repo,
            "size_hint": spec.size_hint,
        }

    model_dir, repo = _resolve_modelscope(spec, config_path)
    return {
        "key": spec.key,
        "label": spec.label,
        "ready": ready,
        "path": str(model_dir),
        "repo": repo,
        "size_hint": spec.size_hint,
    }


def status_report(
    keys: list[str] | None = None,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    selected = keys or list(MODEL_SPECS)
    return [spec_status(MODEL_SPECS[key], config_path) for key in selected]


def print_status(keys: list[str] | None = None, *, config_path: Path = DEFAULT_CONFIG) -> int:
    rows = status_report(keys, config_path=config_path)
    ready_count = sum(1 for row in rows if row["ready"])
    print(f"Model weights ({ready_count}/{len(rows)} ready)\n")
    for row in rows:
        mark = "OK" if row["ready"] else "MISSING"
        print(f"  [{mark:7}] {row['label']} ({row['size_hint']})")
        print(f"           {row['path']}")
    return 0 if ready_count == len(rows) else 1


def download_spec(
    spec: ModelSpec,
    *,
    config_path: Path = DEFAULT_CONFIG,
    force: bool = False,
) -> Path:
    if not force and is_spec_ready(spec, config_path):
        path = spec_status(spec, config_path)["path"]
        print(f"[skip] {spec.label} already present at {path}")
        return Path(str(path))

    print(f"[download] {spec.label} ({spec.size_hint}) ...")

    if spec.kind == "autore":
        from services.kg.autore_runtime import ensure_autore_models

        return ensure_autore_models(allow_download=True)

    if spec.key == "whisper":
        from services.parse.whisper_runtime import ensure_whisper_model

        model_dir, repo = _whisper_paths(config_path)
        return ensure_whisper_model(model_dir, repo, allow_download=True)

    model_dir, repo = _resolve_modelscope(spec, config_path)
    path = ensure_model_dir(model_dir=model_dir, modelscope_repo=repo)
    print(f"[done] {spec.label} -> {path}")
    return path


def download_profile(
    profile: str,
    *,
    config_path: Path = DEFAULT_CONFIG,
    force: bool = False,
    keys: list[str] | None = None,
) -> int:
    if keys:
        selected = keys
    elif profile in PROFILES:
        selected = PROFILES[profile]
    else:
        if profile not in MODEL_SPECS:
            print(
                f"Unknown profile or model key: {profile}\n"
                f"Profiles: {', '.join(PROFILES)}\n"
                f"Keys: {', '.join(MODEL_SPECS)}",
                file=sys.stderr,
            )
            return 2
        selected = [profile]

    print(f"Downloading profile={profile!r} ({len(selected)} model(s))\n")
    errors: list[str] = []
    for key in selected:
        spec = MODEL_SPECS[key]
        try:
            download_spec(spec, config_path=config_path, force=force)
        except Exception as exc:
            errors.append(f"{spec.label}: {exc}")
            print(f"[error] {spec.label}: {exc}", file=sys.stderr)

    print()
    print_status(selected, config_path=config_path)
    if errors:
        print(f"\n{len(errors)} download(s) failed.", file=sys.stderr)
        return 1
    return 0


def confirm_large_download(profile: str, keys: list[str] | None = None) -> bool:
    selected = keys or PROFILES.get(profile, [])
    heavy = [MODEL_SPECS[k] for k in selected if k in {"visual", "autore"}]
    if not heavy:
        return True
    print("The following large downloads are included:")
    for spec in heavy:
        print(f"  - {spec.label} ({spec.size_hint})")
    try:
        answer = input("Continue? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}
