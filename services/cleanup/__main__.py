"""CLI: python -m services.cleanup [assets|sessions|purge] [--dry-run|--execute]"""

from __future__ import annotations

import argparse
import asyncio
import json

from services.cleanup.assets import cleanup_orphan_assets
from services.cleanup.purge import purge_dev_data
from services.cleanup.sessions import cleanup_all_sessions
from services.cleanup.types import CleanupReport


def _print_report(name: str, report: CleanupReport) -> None:
    print(f"\n=== {name} ===")
    print(f"scanned: {report.scanned}, deleted: {report.deleted}, skipped: {report.skipped}")
    if report.deleted_ids:
        print("ids:", ", ".join(report.deleted_ids[:20]), ("..." if len(report.deleted_ids) > 20 else ""))
    for err in report.errors:
        print(f"  error: {err}")


async def _run(args: argparse.Namespace) -> None:
    dry_run = not args.execute
    if args.target == "assets":
        report = await cleanup_orphan_assets(dry_run=dry_run, include_disk=args.include_disk)
        _print_report("assets", report)
    elif args.target == "sessions":
        report = await cleanup_all_sessions(dry_run=dry_run, only_idle=not args.all_status)
        _print_report("sessions", report)
    else:
        results = await purge_dev_data(dry_run=dry_run, include_disk=args.include_disk)
        _print_report("assets", results["assets"])
        _print_report("sessions", results["sessions"])


def main() -> None:
    parser = argparse.ArgumentParser(description="ContextMap cleanup utility")
    parser.add_argument("target", choices=["assets", "sessions", "purge"], default="purge", nargs="?")
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default unless --execute)")
    parser.add_argument("--execute", action="store_true", help="Perform deletion")
    parser.add_argument("--include-disk", action="store_true", help="Also remove raw/processed files (assets)")
    parser.add_argument("--all-status", action="store_true", help="Include non-idle sessions")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
