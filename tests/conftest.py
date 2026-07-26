"""Shared pytest fixtures for async DB and singleton isolation."""

from __future__ import annotations

import pytest

from database.session import dispose_engine


@pytest.fixture(autouse=True)
async def isolate_db_engine():
    """Drop the module-level async engine after each test.

    SQLAlchemy's async engine binds to the event loop that first created it.
    Without disposal, later tests running on a different loop fail with
    "Future attached to a different loop" or asyncpg "operation in progress".
    """
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
def isolate_assets_manager():
    """Reset AssetsManager singleton between tests."""
    yield
    from core.assets_manager import AssetsManager

    instance = AssetsManager._instance
    if instance is not None:
        instance._running = False
        worker = instance._worker_task
        if worker is not None and not worker.done():
            worker.cancel()
        instance._worker_task = None
    AssetsManager._instance = None
