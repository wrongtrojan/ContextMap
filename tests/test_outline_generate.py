"""Integration tests for outline generation CLI flow."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from database.enums import AssetModality, AssetStatus
from database.repositories import AssetRepo, OutlineRepo
from database.session import get_session
from services.outline.generate_outline import (
    _should_skip_outline,
    generate_outline_for_processed_dir,
)
from tests.helpers.assets import resolve_asset_for_processed_dir

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTORE_DIR = (
    PROJECT_ROOT
    / "storage/assets/processed/pdf/Xue 等 - 2024 - AutoRE Document-Level Relation Extraction with Large Language Models"
)


def _ready_asset(metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=AssetStatus.READY,
        metadata=metadata,
    )


def test_should_skip_outline_cache_hit() -> None:
    fp = {"prompt_version": "2026-07-26", "loader_version": "2026-07-26"}
    asset = _ready_asset({"outline_fingerprint": fp})
    skip, reason = _should_skip_outline(asset, True, fp, force=False, skip_if_ready=True)
    assert skip is True
    assert reason == "cache_hit"


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
@pytest.mark.asyncio
async def test_dry_run_does_not_persist() -> None:
    summary = await generate_outline_for_processed_dir(
        AUTORE_DIR,
        dry_run=True,
        skip_if_ready=False,
    )
    assert summary["action"] == "dry_run"
    assert summary["coverage"]["context_chars"] > 0


def _find_processed_audio_dir() -> Path | None:
    audio_root = PROJECT_ROOT / "storage/assets/processed/audio"
    if not audio_root.is_dir():
        return None
    for path in sorted(audio_root.iterdir()):
        if path.is_dir() and any(path.glob("*_middle.json")):
            return path
    return None


AUDIO_DIR = _find_processed_audio_dir() or PROJECT_ROOT / "storage/assets/processed/audio/_missing"


@pytest.mark.skipif(not AUDIO_DIR.exists(), reason="CSAPP audio sample not present")
@pytest.mark.asyncio
async def test_dry_run_audio_included() -> None:
    summary = await generate_outline_for_processed_dir(
        AUDIO_DIR,
        dry_run=True,
        skip_if_ready=False,
    )
    assert summary["action"] == "dry_run"
    assert summary["modality"] == "audio"
    assert summary["coverage"]["segments"] > 0
    assert summary["coverage"]["duration_sec"] > 0


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
@pytest.mark.asyncio
async def test_generate_outline_with_mock_llm() -> None:
    async with get_session() as session:
        asset_id = await resolve_asset_for_processed_dir(
            session,
            AUTORE_DIR,
            project_root=PROJECT_ROOT,
        )
    assert asset_id is not None

    mock_graph_result = {
        "valid": True,
        "failed": False,
        "title": "AutoRE Outline",
        "tree": [
            {
                "heading": "Introduction",
                "summary": "Document-level relation extraction.",
                "anchor": 1,
                "sub_points": [],
            }
        ],
        "repair_count": 0,
    }

    with patch("services.outline.generate_outline.get_outline_graph") as mock_graph:
        mock_graph.return_value.ainvoke = AsyncMock(return_value=mock_graph_result)
        first = await generate_outline_for_processed_dir(
            AUTORE_DIR,
            force=True,
            asset_id=asset_id,
        )
        assert first["action"] == "generated"
        assert first["node_count"] == 1

        second = await generate_outline_for_processed_dir(
            AUTORE_DIR,
            force=False,
            skip_if_ready=True,
            asset_id=asset_id,
        )
        assert second["action"] == "skipped"

    async with get_session() as session:
        outline = await OutlineRepo(session).get_by_asset(asset_id)
        assert outline is not None
        assert outline.title == "AutoRE Outline"
