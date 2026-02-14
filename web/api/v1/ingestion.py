import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,UploadFile, File

# Import our orchestrator gateway
from web.orchestrator import get_orchestrator, AgentLogicOrchestrator

# Standardized logging for Ingestion API
logger = logging.getLogger("IngestionAPI")

router = APIRouter()

@router.post("/sync")
async def trigger_global_sync(
    background_tasks: BackgroundTasks, 
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Endpoint to trigger the global asset ingestion process.
    Uses BackgroundTasks to ensure the HTTP request returns immediately 
    while the GPU-heavy processing runs in the background.
    """
    # 1. Pre-check: Is the system already busy?
    task_id = "global_sync_task" 
    if not core.state_manager.acquire_ingestion_lock(task_id):
        logger.warning("Sync request REJECTED: System is busy.")
        raise HTTPException(
            status_code=409, 
            detail="System is currently busy."
        )

    # 2. Trigger the task in background
    logger.info("Sync request ACCEPTED: Launching background ingestion stream.")
    background_tasks.add_task(core.trigger_sync)
    
    return {
        "status": "accepted",
        "message": "Global synchronization started. Poll /status for progress."
    }

@router.get("/status")
async def get_task_status(
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Endpoint for the frontend to poll the real-time progress of the ingestion pipeline.
    Returns VRAM lock status, active assets, and granular component progress.
    """
    state = core.get_system_snapshot()
    return state

@router.post("/upload")
async def upload_academic_asset(
    file: UploadFile = File(...),
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Receives a file and stores it in the corresponding raw_files directory.
    This is the entry point for the frontend to introduce new assets.
    """
    try:
        filename = file.filename
        extension = filename.split(".")[-1].lower()
        
        # Determine destination based on file extension
        if extension == "pdf":
            target_dir = Path("storage/raw_files/PDF")
        elif extension in ["mp4", "mkv", "mov"]:
            target_dir = Path("storage/raw_files/video")
        else:
            return {"status": "error", "message": f"Unsupported file type: {extension}"}

        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / filename

        # Efficiently save the uploaded file
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"Successfully uploaded {filename} to {target_dir}")
        return {
            "status": "success",
            "filename": filename,
            "path": str(save_path)
        }
    except Exception as e:
        logger.error(f"Failed to upload file: {str(e)}")
        return {"status": "error", "message": str(e)}