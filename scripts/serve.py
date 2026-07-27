"""Start backend / frontend dev servers from the CLI."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from paths import PROJECT_ROOT

_FRONTEND_DIR = PROJECT_ROOT / "web" / "frontend"


def _popen(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    print(f"$ {' '.join(cmd)}")
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=merged,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def serve_backend(*, host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> int:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "web.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    proc = _popen(cmd, cwd=PROJECT_ROOT)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        return proc.wait()


def serve_frontend(
    *,
    host: str = "0.0.0.0",
    port: int = 3000,
    api_base: str | None = None,
    production: bool = False,
) -> int:
    env: dict[str, str] = {}
    if api_base:
        env["NEXT_PUBLIC_API_BASE_URL"] = api_base.rstrip("/")

    if production:
        build = subprocess.run(["npm", "run", "build"], cwd=_FRONTEND_DIR, check=False)
        if build.returncode != 0:
            return build.returncode
        cmd = ["npm", "run", "start", "--", "-H", host, "-p", str(port)]
    else:
        cmd = ["npm", "run", "dev", "--", "-H", host, "-p", str(port)]

    proc = _popen(cmd, cwd=_FRONTEND_DIR, env=env)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        return proc.wait()


def serve_all(
    *,
    host: str = "0.0.0.0",
    backend_port: int = 8000,
    frontend_port: int = 3000,
    api_base: str | None = None,
    reload: bool = True,
) -> int:
    api = api_base or f"http://127.0.0.1:{backend_port}"
    backend = _popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "web.main:app",
            "--host",
            host,
            "--port",
            str(backend_port),
            *(["--reload"] if reload else []),
        ],
        cwd=PROJECT_ROOT,
    )
    time.sleep(1.0)
    frontend = _popen(
        ["npm", "run", "dev", "--", "-H", host, "-p", str(frontend_port)],
        cwd=_FRONTEND_DIR,
        env={"NEXT_PUBLIC_API_BASE_URL": api.rstrip("/")},
    )

    def _shutdown(*_args: object) -> None:
        for proc in (frontend, backend):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            for proc in (backend, frontend):
                code = proc.poll()
                if code is not None:
                    _shutdown()
                    return code
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()
        return 0
