"""Tests for outline persistence and optional JSON export."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from database.enums import AssetModality, AssetStatus
from database.repositories import AssetRepo, OutlineRepo
from database.schemas import AssetCreate
from database.session import get_session
from paths import PROJECT_ROOT
from services.outline.persist import (
    export_outline_json,
    load_outline_json_fallback,
    outline_to_api_payload,
    should_export_json,
)
from tests.helpers.assets import resolve_asset_for_processed_dir
from tests.helpers.corpus_paths import AUTORE_DIR


def test_should_export_json_cli_overrides_config() -> None:
    config = {"persist": {"export_json": False}}
    assert should_export_json(config=config, cli_export=True) is True
    assert should_export_json(config=config, cli_export=None) is False


def test_export_outline_json_writes_file(tmp_path: Path) -> None:
    asset_id = uuid.uuid4()
    tree = [{"heading": "Intro", "summary": "s", "anchor": 1, "sub_points": []}]
    export_path = export_outline_json(
        tmp_path,
        asset_id=asset_id,
        title="Demo",
        tree=tree,
        model_id="deepseek-chat",
    )
    assert export_path.is_file()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["asset_id"] == str(asset_id)
    assert payload["title"] == "Demo"
    assert payload["outline"]["outline"] == tree
    assert load_outline_json_fallback(tmp_path) == payload


def test_outline_to_api_payload_shape() -> None:
    from datetime import datetime, timezone

    from database.schemas import OutlineRead

    outline = OutlineRead(
        asset_id=uuid.uuid4(),
        title="T",
        tree=[{"heading": "H", "summary": "S", "anchor": 1, "sub_points": []}],
        model_id="m",
        generated_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = outline_to_api_payload(outline)
    assert payload["title"] == "T"
    assert payload["outline"]["outline"][0]["heading"] == "H"


@pytest.mark.asyncio
async def test_persist_outline_writes_pg_row(tmp_path: Path) -> None:
    from services.outline.persist import persist_outline

    async with get_session() as session:
        created = await AssetRepo(session).create(
            AssetCreate(
                name="persist-test",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/test.pdf",
                processed_path="storage/assets/processed/pdf/persist-test",
                file_hash=f"persist-{uuid.uuid4().hex}",
                status=AssetStatus.READY,
                metadata={"ingest_fingerprint": {"loader_version": "2026-07-26"}},
            )
        )
        asset_id = created.id

    try:
        tree = [{"heading": "Section", "summary": "text", "anchor": 1, "sub_points": []}]
        fp = {"prompt_version": "2026-07-26", "loader_version": "2026-07-26"}

        async with get_session() as session:
            outline = await persist_outline(
                session,
                asset_id=asset_id,
                title="Persisted",
                tree=tree,
                model_id="deepseek-chat",
                outline_fingerprint=fp,
            )
            assert outline.title == "Persisted"
            assert len(outline.tree) == 1

        async with get_session() as session:
            asset = await AssetRepo(session).get_by_id(asset_id)
            stored = await OutlineRepo(session).get_by_asset(asset_id)
            assert asset is not None
            assert asset.metadata.get("ingest_fingerprint") is not None
            assert asset.metadata.get("outline_fingerprint") == fp
            assert stored is not None
            assert stored.title == "Persisted"
    finally:
        async with get_session() as session:
            await AssetRepo(session).delete(asset_id)


@pytest.mark.skipif(not AUTORE_DIR.exists(), reason="AutoRE sample not present")
@pytest.mark.asyncio
async def test_generate_outline_export_json_optional() -> None:
    from services.outline.generate_outline import generate_outline_for_processed_dir

    export_file = AUTORE_DIR / "summary_outline.json"
    created_export = False
    if export_file.exists():
        export_file.unlink()

    try:
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
            "title": "Export Test",
            "tree": [{"heading": "H", "summary": "S", "anchor": 1, "sub_points": []}],
            "repair_count": 0,
        }

        with patch("services.outline.generate_outline.get_outline_graph") as mock_graph:
            mock_graph.return_value.ainvoke = AsyncMock(return_value=mock_graph_result)
            without_export = await generate_outline_for_processed_dir(
                AUTORE_DIR,
                force=True,
                export_json=False,
                asset_id=asset_id,
            )
            assert without_export["action"] == "generated"
            assert "export_path" not in without_export
            assert not export_file.exists()

            with_export = await generate_outline_for_processed_dir(
                AUTORE_DIR,
                force=True,
                export_json=True,
                asset_id=asset_id,
            )
            assert with_export.get("export_path") == str(export_file)
            assert export_file.is_file()
            created_export = True
    finally:
        if created_export and export_file.exists():
            export_file.unlink()
