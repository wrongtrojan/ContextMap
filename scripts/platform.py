"""Docker, directories, secrets, and health checks for ContextMap CLI."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from paths import LOCAL_SECRETS_ENV, PROJECT_ROOT, RAW_AUDIO_DIR, RAW_PDF_DIR, RAW_VIDEO_DIR
from core.settings.secrets import read_secrets_file, upsert_secret


def ensure_project_dirs() -> None:
    for path in (
        PROJECT_ROOT / "storage" / "local",
        PROJECT_ROOT / "storage" / "db_data" / "postgres",
        PROJECT_ROOT / "storage" / "db_data" / "minio",
        RAW_PDF_DIR,
        RAW_VIDEO_DIR,
        RAW_AUDIO_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        check=check,
        text=True,
    )


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_compose_cmd() -> list[str]:
    if shutil.which("docker"):
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return ["docker", "compose"]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise RuntimeError("docker compose or docker-compose not found")


def docker_up() -> None:
    if not docker_available():
        raise RuntimeError("Docker is not installed or not on PATH")
    cmd = docker_compose_cmd() + ["-f", "deploy/docker-compose.yml", "up", "-d"]
    _run(cmd)


def docker_down() -> None:
    cmd = docker_compose_cmd() + ["-f", "deploy/docker-compose.yml", "down"]
    _run(cmd)


def docker_status() -> int:
    cmd = docker_compose_cmd() + ["-f", "deploy/docker-compose.yml", "ps"]
    return _run(cmd, check=False).returncode


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def setup_secrets_interactive(*, non_interactive: bool = False) -> None:
    existing = read_secrets_file(LOCAL_SECRETS_ENV)
    if existing.get("DEEPSEEK_API_KEY"):
        hint = existing["DEEPSEEK_API_KEY"][-4:]
        print(f"DEEPSEEK_API_KEY already set (…{hint}) — skipping.")
        return

    if non_interactive:
        if os.getenv("DEEPSEEK_API_KEY"):
            upsert_secret("DEEPSEEK_API_KEY", os.environ["DEEPSEEK_API_KEY"])
            print("Wrote DEEPSEEK_API_KEY from environment to secrets.env")
        else:
            print("No DEEPSEEK_API_KEY in env; configure later via Workbench Settings.")
        return

    print("DeepSeek API key (optional now; required for chat/outline). Press Enter to skip.")
    try:
        import getpass

        value = getpass.getpass("DEEPSEEK_API_KEY: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped API key setup.")
        return
    if value:
        upsert_secret("DEEPSEEK_API_KEY", value)
        print(f"Saved to {LOCAL_SECRETS_ENV}")


def doctor_report() -> dict[str, object]:
    from scripts.model_catalog import PROFILES
    from scripts.models import status_report

    models = status_report(PROFILES["core"])
    missing_models = [row["label"] for row in models if not row["ready"]]
    secrets = read_secrets_file(LOCAL_SECRETS_ENV)
    return {
        "python_ok": sys.version_info >= (3, 11),
        "docker_ok": docker_available(),
        "postgres_up": port_open("127.0.0.1", 5432),
        "minio_up": port_open("127.0.0.1", 9000),
        "api_key_set": bool(secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")),
        "models_ready": not missing_models,
        "missing_models": missing_models,
    }


def print_doctor() -> int:
    report = doctor_report()
    checks = [
        ("Python >= 3.11", report["python_ok"]),
        ("Docker CLI", report["docker_ok"]),
        ("Postgres :5432", report["postgres_up"]),
        ("MinIO :9000", report["minio_up"]),
        ("DEEPSEEK_API_KEY", report["api_key_set"]),
        ("Core model weights", report["models_ready"]),
    ]
    print("ContextMap doctor\n")
    failed = 0
    for label, ok in checks:
        mark = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark:4}] {label}")
    missing = report["missing_models"]
    if missing:
        print("\n  Missing models (run: ./contextmap.py models download):")
        for name in missing:
            print(f"    - {name}")
    return 1 if failed else 0
