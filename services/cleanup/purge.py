"""Combined dev purge."""

from __future__ import annotations

from services.cleanup.assets import cleanup_orphan_assets
from services.cleanup.sessions import cleanup_all_sessions
from services.cleanup.types import CleanupReport


async def purge_dev_data(*, dry_run: bool = True, include_disk: bool = False) -> dict[str, CleanupReport]:
    assets = await cleanup_orphan_assets(dry_run=dry_run, include_disk=include_disk)
    sessions = await cleanup_all_sessions(dry_run=dry_run, only_idle=True)
    return {"assets": assets, "sessions": sessions}
