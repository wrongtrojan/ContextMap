import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile

from core.assets_manager import create_asset_for_upload, get_assets_manager, load_pipeline_config
from database.enums import AssetModality
from paths import PROJECT_ROOT, RAW_AUDIO_DIR, RAW_PDF_DIR, RAW_VIDEO_DIR

logger = logging.getLogger("UploadAPI")
router = APIRouter()

_MODALITY_DIRS = {
    AssetModality.PDF: RAW_PDF_DIR,
    AssetModality.VIDEO: RAW_VIDEO_DIR,
    AssetModality.AUDIO: RAW_AUDIO_DIR,
}


def _detect_modality(filename: str) -> AssetModality | None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return AssetModality.PDF
    if ext in {".mp4", ".mkv", ".mov", ".webm", ".avi"}:
        return AssetModality.VIDEO
    if ext in {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}:
        return AssetModality.AUDIO
    return None


@router.post("/file")
async def upload_academic_asset(file: UploadFile = File(...)):
    filename = file.filename or "upload.bin"
    modality = _detect_modality(filename)
    if modality is None:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")

    target_dir = _MODALITY_DIRS[modality]
    target_dir.mkdir(parents=True, exist_ok=True)
    save_path = target_dir / filename
    rel_path = save_path.relative_to(PROJECT_ROOT).as_posix()

    try:
        size = 0
        async with aiofiles.open(save_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                size += len(content)
                await out_file.write(content)

        asset = await create_asset_for_upload(
            name=filename,
            modality=modality,
            raw_path=rel_path,
            file_size_bytes=size,
        )

        if load_pipeline_config().get("auto_start_on_upload", True):
            await get_assets_manager().enqueue(asset.id)

        return {
            "status": "success",
            "asset_id": str(asset.id),
            "current_state": asset.status.value,
            "message": "File uploaded and pipeline enqueued.",
        }
    except Exception as exc:
        logger.error("Upload failed for %s: %s", filename, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
