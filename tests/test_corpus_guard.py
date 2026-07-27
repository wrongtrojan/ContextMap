"""Pytest wrapper for shared corpus embedding health check."""

from __future__ import annotations

import pytest

from tests.helpers.corpus_guard import assert_autore_embeddings_healthy


@pytest.mark.asyncio
async def test_autore_embeddings_healthy() -> None:
    await assert_autore_embeddings_healthy()
