import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.assets_manager import get_assets_manager
from core.env import load_dotenv, load_secrets, llm_api_key_configured
from paths import RAW_AUDIO_DIR, RAW_PDF_DIR, RAW_VIDEO_DIR
from web.api.v1.assets import router as assets_router
from web.api.v1.chats import router as chats_router
from web.api.v1.settings import router as settings_router
from web.api.v1.status import router as status_router
from web.api.v1.kg import router as kg_router
from web.api.v1.upload import router as upload_router

load_secrets()
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [WEB-MAIN] - %(levelname)s - %(message)s",
)
logger = logging.getLogger("WebMain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- [System Startup] ---")
    for directory in (RAW_PDF_DIR, RAW_VIDEO_DIR, RAW_AUDIO_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    from services.cleanup.session_delete_queue import get_session_delete_queue

    manager = get_assets_manager()
    await manager.start()
    await get_session_delete_queue().start()
    yield
    await get_session_delete_queue().stop()
    await manager.stop()
    logger.info("--- [System Shutdown] ---")


app = FastAPI(
    title="ContextMap API",
    description="后端 API：多模态资产 LangGraph 流水线 + 推理。",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

assets_raw = Path("storage/assets/raw")
if assets_raw.exists():
    app.mount("/raw/assets", StaticFiles(directory=str(assets_raw)), name="raw_assets")

app.include_router(upload_router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(assets_router, prefix="/api/v1/assets", tags=["Assets"])
app.include_router(kg_router, prefix="/api/v1/kg", tags=["KG"])
app.include_router(status_router, prefix="/api/v1/status", tags=["Status"])
app.include_router(chats_router, prefix="/api/v1/chats", tags=["Chats"])
app.include_router(settings_router, prefix="/api/v1/settings", tags=["Settings"])


@app.get("/")
async def root():
    return {
        "message": "ContextMap API is online.",
        "api_v1": "/api/v1",
        "docs": "/docs",
        "llm_configured": llm_api_key_configured(),
    }
