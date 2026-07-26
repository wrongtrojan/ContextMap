import uuid

import pytest

from database.enums import AssetModality, AssetStatus, PipelineEventType
from database.repositories import AssetRepo, PipelineEventRepo
from database.schemas import AssetCreate
from database.session import get_session


@pytest.mark.asyncio
async def test_pipeline_event_repo_append_and_list():
    async with get_session() as session:
        asset_repo = AssetRepo(session)
        event_repo = PipelineEventRepo(session)
        asset = await asset_repo.create(
            AssetCreate(
                name="pipeline-event-test",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/test.pdf",
                status=AssetStatus.RAW,
            )
        )
        await event_repo.append(
            asset.id,
            PipelineEventType.STEP_START,
            step_name="parse",
            to_status=AssetStatus.RECOGNIZING,
            detail={"message": "started"},
        )
        events = await event_repo.list_recent(asset.id, limit=5)
        assert len(events) == 1
        assert events[0].step_name == "parse"
        await asset_repo.delete(asset.id)


@pytest.mark.asyncio
async def test_assets_manager_graph_build():
    from core.assets_manager import AssetsManager, build_asset_graph

    manager = AssetsManager()
    graph = build_asset_graph(manager)
    assert graph is not None
    drawn = graph.get_graph()
    node_names = set(drawn.nodes.keys())
    assert "kg_extract" in node_names


@pytest.mark.asyncio
async def test_create_asset_for_upload():
    from core.assets_manager import create_asset_for_upload

    asset = await create_asset_for_upload(
        name="unit-test.pdf",
        modality=AssetModality.PDF,
        raw_path="storage/assets/raw/pdf/unit-test.pdf",
        file_size_bytes=123,
    )
    assert asset.status == AssetStatus.RAW
    async with get_session() as session:
        await AssetRepo(session).delete(asset.id)
