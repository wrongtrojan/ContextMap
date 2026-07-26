import uuid

import pytest

from database.enums import AssetModality, AssetStatus, KgStatus
from database.repositories import AssetRepo, KgJobRepo
from database.schemas import AssetCreate
from database.session import get_session


@pytest.mark.asyncio
async def test_kg_job_repo_lifecycle():
    asset_id = uuid.uuid4()
    async with get_session() as session:
        asset_repo = AssetRepo(session)
        job_repo = KgJobRepo(session)
        await asset_repo.create(
            AssetCreate(
                name="kg-job-test",
                modality=AssetModality.AUDIO,
                raw_path="storage/assets/raw/audio/x.wav",
                status=AssetStatus.RAW,
            ),
            asset_id=asset_id,
        )
        job = await job_repo.upsert_job(asset_id, chunks_total=3)
        assert job.chunks_total == 3
        await job_repo.update_progress(asset_id, chunks_processed=2, triples_extracted=4)
        finished = await job_repo.mark_status(asset_id, KgStatus.READY, triples_extracted=4)
        assert finished is not None
        assert finished.status == KgStatus.READY
        assert finished.triples_extracted == 4
        await asset_repo.delete(asset_id)


@pytest.mark.asyncio
async def test_asset_repo_update_kg_status():
    asset_id = uuid.uuid4()
    async with get_session() as session:
        repo = AssetRepo(session)
        await repo.create(
            AssetCreate(
                name="kg-status-test",
                modality=AssetModality.PDF,
                raw_path="storage/assets/raw/pdf/x.pdf",
                status=AssetStatus.RAW,
            ),
            asset_id=asset_id,
        )
        updated = await repo.update_kg_status(asset_id, KgStatus.READY, triple_count=7)
        assert updated is not None
        assert updated.kg_status == KgStatus.READY
        assert updated.triple_count == 7
        await repo.delete(asset_id)
