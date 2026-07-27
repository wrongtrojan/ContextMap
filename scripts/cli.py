"""ContextMap unified CLI."""

from __future__ import annotations

import argparse
import sys

from scripts.calibrator import apply_calibration, print_calibrate_report, calibrate_report
from scripts.model_catalog import DEFAULT_PROFILE, PROFILES
from scripts.models import confirm_large_download, download_profile, print_status
from scripts.platform import (
    docker_down,
    docker_status,
    docker_up,
    ensure_project_dirs,
    print_doctor,
    setup_secrets_interactive,
)
from scripts.serve import serve_all, serve_backend, serve_frontend


def _config_path(args: argparse.Namespace):
    from pathlib import Path

    from scripts.model_catalog import DEFAULT_CONFIG

    if getattr(args, "config", None):
        return Path(args.config)
    return DEFAULT_CONFIG


def _cmd_setup(args: argparse.Namespace) -> int:
    config_path = _config_path(args)
    ensure_project_dirs()
    print("ContextMap setup\n")

    if not args.skip_docker:
        try:
            docker_up()
        except Exception as exc:
            print(f"[warn] Docker stack not started: {exc}", file=sys.stderr)
    else:
        print("[skip] Docker")

    if not args.skip_calibrate:
        if args.apply_calibrate:
            apply_calibration(config_path=config_path)
        print_calibrate_report(calibrate_report(config_path=config_path))
    else:
        print("[skip] Calibrate")

    if not args.skip_secrets:
        setup_secrets_interactive(non_interactive=args.non_interactive)
    else:
        print("[skip] Secrets")

    if not args.skip_models:
        if not args.yes and not confirm_large_download(args.profile):
            print("Model download cancelled.")
            return 0
        return download_profile(args.profile, config_path=config_path, force=args.force)
    print("[skip] Model download")
    print("\nNext: ./contextmap.py serve all")
    return 0


def _cmd_models_download(args: argparse.Namespace) -> int:
    config_path = _config_path(args)
    keys = args.section or None
    profile = args.profile if not keys else "custom"
    if not args.yes and not confirm_large_download(profile, keys=keys):
        print("Cancelled.")
        return 0
    if keys:
        return download_profile(profile, config_path=config_path, force=args.force, keys=keys)
    return download_profile(args.profile, config_path=config_path, force=args.force)


def _cmd_calibrate(args: argparse.Namespace) -> int:
    config_path = _config_path(args)
    if args.apply:
        path = apply_calibration(config_path=config_path)
        print(f"Updated {path}")
    print_calibrate_report(calibrate_report(config_path=config_path))
    if not args.apply:
        print("\nRun: ./contextmap.py calibrate --apply")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextmap",
        description="ContextMap bootstrap, models, and local dev servers",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to contextmap.yaml (default: configs/contextmap.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="First-run: dirs, docker, calibrate, secrets, models")
    setup.add_argument("--skip-docker", action="store_true")
    setup.add_argument("--skip-models", action="store_true")
    setup.add_argument("--skip-secrets", action="store_true")
    setup.add_argument("--skip-calibrate", action="store_true")
    setup.add_argument("--apply-calibrate", action="store_true", help="Write device flags to yaml")
    setup.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE)
    setup.add_argument("--force", action="store_true", help="Re-download even if present")
    setup.add_argument("-y", "--yes", action="store_true", help="Skip large-download confirmation")
    setup.add_argument("--non-interactive", action="store_true")
    setup.set_defaults(func=_cmd_setup)

    models = sub.add_parser("models", help="Model weight pre-download")
    models_sub = models.add_subparsers(dest="models_cmd", required=True)

    models_download = models_sub.add_parser("download", help="Download ModelScope / AutoRE weights")
    models_download.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=DEFAULT_PROFILE,
        help=f"Download bundle (default: {DEFAULT_PROFILE})",
    )
    models_download.add_argument(
        "--section",
        action="append",
        metavar="KEY",
        help="Download one model key (embedding, whisper, reranker, visual, autore)",
    )
    models_download.add_argument("--force", action="store_true")
    models_download.add_argument("-y", "--yes", action="store_true")
    models_download.set_defaults(func=_cmd_models_download)

    models_status = models_sub.add_parser("status", help="Show which weights are present")
    models_status.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="all",
        help="Limit status to a profile's models",
    )

    def _cmd_models_status(args: argparse.Namespace) -> int:
        keys = PROFILES.get(args.profile, list(PROFILES["all"]))
        return print_status(keys, config_path=_config_path(args))

    models_status.set_defaults(func=_cmd_models_status)

    calibrate = sub.add_parser("calibrate", help="Detect GPU and recommend device settings")
    calibrate.add_argument("--apply", action="store_true")
    calibrate.set_defaults(func=_cmd_calibrate)

    doctor = sub.add_parser("doctor", help="Check docker, ports, secrets, and models")
    doctor.set_defaults(func=lambda _args: print_doctor())

    docker = sub.add_parser("docker", help="Manage Postgres/MinIO compose stack")
    docker_sub = docker.add_subparsers(dest="docker_cmd", required=True)
    docker_sub.add_parser("up").set_defaults(func=lambda _a: docker_up() or 0)
    docker_sub.add_parser("down").set_defaults(func=lambda _a: docker_down() or 0)
    docker_sub.add_parser("status").set_defaults(func=lambda _a: docker_status())

    serve = sub.add_parser("serve", help="Run backend and/or frontend")
    serve_sub = serve.add_subparsers(dest="serve_cmd", required=True)

    serve_backend_p = serve_sub.add_parser("backend", help="uvicorn web.main:app")
    serve_backend_p.add_argument("--host", default="0.0.0.0")
    serve_backend_p.add_argument("--port", type=int, default=8000)
    serve_backend_p.add_argument("--reload", action="store_true", default=True)
    serve_backend_p.add_argument("--no-reload", action="store_false", dest="reload")
    serve_backend_p.set_defaults(
        func=lambda a: serve_backend(host=a.host, port=a.port, reload=a.reload)
    )

    serve_frontend_p = serve_sub.add_parser("frontend", help="next dev or next start")
    serve_frontend_p.add_argument("--host", default="0.0.0.0")
    serve_frontend_p.add_argument("--port", type=int, default=3000)
    serve_frontend_p.add_argument("--api-base", default=None)
    serve_frontend_p.add_argument("--production", action="store_true")
    serve_frontend_p.set_defaults(
        func=lambda a: serve_frontend(
            host=a.host,
            port=a.port,
            api_base=a.api_base,
            production=a.production,
        )
    )

    serve_all_p = serve_sub.add_parser("all", help="Backend + frontend together")
    serve_all_p.add_argument("--host", default="0.0.0.0")
    serve_all_p.add_argument("--backend-port", type=int, default=8000)
    serve_all_p.add_argument("--frontend-port", type=int, default=3000)
    serve_all_p.add_argument("--api-base", default=None)
    serve_all_p.add_argument("--no-reload", action="store_true")
    serve_all_p.set_defaults(
        func=lambda a: serve_all(
            host=a.host,
            backend_port=a.backend_port,
            frontend_port=a.frontend_port,
            api_base=a.api_base,
            reload=not a.no_reload,
        )
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return int(func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
