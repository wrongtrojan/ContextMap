"""
Assets pipeline orchestration: LangGraph parse → outline → ingest → kg_extract.

Usage:
  python -m core.assets_manager --asset-id <uuid>
  python -m core.assets_manager --raw-path storage/assets/raw/pdf/foo.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph

from database.enums import AssetModality, AssetStatus, KgStatus, PipelineEventType
from database.repositories import AssetRepo, PipelineEventRepo
from database.schemas import AssetCreate, AssetRead
from database.session import get_session
from paths import (
    CONTEXTMAP_CONFIG,
    PROCESSED_AUDIO_DIR,
    PROCESSED_PDF_DIR,
    PROCESSED_VIDEO_DIR,
    PROJECT_ROOT,
    RAW_AUDIO_DIR,
    RAW_PDF_DIR,
    RAW_VIDEO_DIR,
)
from services.common.processed_assets import relative_path
from services.ingest.ingest_assets import ingest_processed_dir
from services.outline.generate_outline import generate_outline_for_processed_dir
from services.parse.parse_audio import parse_one as parse_audio_one
from services.parse.parse_pdf import mineru_defaults, parse_one as parse_pdf_one
from services.parse.parse_video import parse_one as parse_video_one
from services.kg.config import load_kg_config
from services.kg.extract_assets import extract_kg_for_asset_sync

logger = logging.getLogger("AssetsManager")

_MODALITY_RAW_DIRS = {
    AssetModality.PDF: RAW_PDF_DIR,
    AssetModality.VIDEO: RAW_VIDEO_DIR,
    AssetModality.AUDIO: RAW_AUDIO_DIR,
}
_MODALITY_PROCESSED_DIRS = {
    AssetModality.PDF: PROCESSED_PDF_DIR,
    AssetModality.VIDEO: PROCESSED_VIDEO_DIR,
    AssetModality.AUDIO: PROCESSED_AUDIO_DIR,
}


class AssetPipelineState(TypedDict, total=False):
    asset_id: str
    modality: str
    raw_path: str
    processed_path: str | None
    step: str
    error: str | None
    parse_action: str | None
    outline_action: str | None
    ingest_action: str | None
    kg_action: str | None


def load_pipeline_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONTEXTMAP_CONFIG
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = {
        "max_concurrent_parse": 2,
        "max_concurrent_whisper": 1,
        "max_concurrent_outline": 3,
        "max_concurrent_ingest": 2,
        "max_concurrent_kg": 1,
        "auto_start_on_upload": True,
    }
    pipeline = dict(data.get("pipeline") or {})
    return {**defaults, **pipeline}


def _raw_path_for_asset(asset: AssetRead) -> Path:
    raw = Path(asset.raw_path)
    if raw.is_absolute():
        return raw
    return PROJECT_ROOT / raw


def _processed_dir_for_asset(asset: AssetRead) -> Path:
    if asset.processed_path:
        processed = Path(asset.processed_path)
        if processed.is_absolute():
            return processed
        return PROJECT_ROOT / asset.processed_path
    raw = _raw_path_for_asset(asset)
    out_root = _MODALITY_PROCESSED_DIRS[asset.modality]
    return out_root / raw.stem


def _run_parse_sync(asset: AssetRead) -> tuple[str, str]:
    raw_path = _raw_path_for_asset(asset)
    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    if asset.modality == AssetModality.PDF:
        defaults = mineru_defaults()
        _, _, action, _ = parse_pdf_one(
            raw_path,
            PROCESSED_PDF_DIR,
            lang=defaults["lang"],
            backend=defaults["backend"],
            parse_method=defaults["parse_method"],
        )
        processed_dir = PROCESSED_PDF_DIR / raw_path.stem
    elif asset.modality == AssetModality.VIDEO:
        _, _, action, _ = parse_video_one(raw_path, PROCESSED_VIDEO_DIR)
        processed_dir = PROCESSED_VIDEO_DIR / raw_path.stem
    elif asset.modality == AssetModality.AUDIO:
        _, _, action, _ = parse_audio_one(raw_path, PROCESSED_AUDIO_DIR)
        processed_dir = PROCESSED_AUDIO_DIR / raw_path.stem
    else:
        raise ValueError(f"Unsupported modality: {asset.modality}")

    processed_rel = relative_path(processed_dir, PROJECT_ROOT)
    return action, processed_rel


class AssetEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, asset_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            dead: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in self._subscribers.get(asset_id, []):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(queue)
            for queue in dead:
                self._subscribers[asset_id].remove(queue)

    def subscribe(self, asset_id: str, *, maxsize: int = 256) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[asset_id].append(queue)
        return queue

    def unsubscribe(self, asset_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(asset_id, [])
        if queue in subs:
            subs.remove(queue)


class AssetsManager:
    _instance: AssetsManager | None = None

    def __new__(cls) -> AssetsManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        cfg = load_pipeline_config()
        self._queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._parse_sem = asyncio.Semaphore(int(cfg["max_concurrent_parse"]))
        self._whisper_sem = asyncio.Semaphore(int(cfg["max_concurrent_whisper"]))
        self._outline_sem = asyncio.Semaphore(int(cfg["max_concurrent_outline"]))
        self._ingest_sem = asyncio.Semaphore(int(cfg["max_concurrent_ingest"]))
        self._kg_sem = asyncio.Semaphore(int(cfg.get("max_concurrent_kg", 1)))
        self._event_bus = AssetEventBus()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._active: set[uuid.UUID] = set()
        self._initialized = True

    @property
    def event_bus(self) -> AssetEventBus:
        return self._event_bus

    async def _emit(
        self,
        asset_id: uuid.UUID,
        event_type: PipelineEventType,
        *,
        step: str | None = None,
        from_status: AssetStatus | None = None,
        to_status: AssetStatus | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        detail = dict(metadata or {})
        if message:
            detail["message"] = message
        async with get_session() as session:
            await PipelineEventRepo(session).append(
                asset_id,
                event_type,
                step_name=step,
                from_status=from_status,
                to_status=to_status,
                detail=detail,
            )
        payload = {
            "type": event_type.value,
            "asset_id": str(asset_id),
            "step": step,
            "status": to_status.value if to_status else None,
            "message": message,
            "metadata": detail,
        }
        await self._event_bus.publish(str(asset_id), payload)

    async def _set_status(self, asset_id: uuid.UUID, status: AssetStatus) -> None:
        async with get_session() as session:
            await AssetRepo(session).update_status(asset_id, status)

    async def enqueue(self, asset_id: uuid.UUID) -> None:
        if asset_id in self._active:
            logger.info("Asset %s already active; skip duplicate enqueue", asset_id)
            return
        await self._queue.put(asset_id)
        logger.info("Enqueued asset %s", asset_id)

    async def retry(self, asset_id: uuid.UUID) -> None:
        async with get_session() as session:
            repo = AssetRepo(session)
            asset = await repo.get_by_id(asset_id)
            if asset is None:
                raise ValueError(f"Asset not found: {asset_id}")
            await repo.update_status(asset_id, AssetStatus.RAW)
        await self.enqueue(asset_id)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("AssetsManager worker started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("AssetsManager worker stopped")

    async def _worker_loop(self) -> None:
        while self._running:
            asset_id = await self._queue.get()
            asyncio.create_task(self._run_pipeline(asset_id))

    async def _run_pipeline(self, asset_id: uuid.UUID) -> None:
        if asset_id in self._active:
            self._queue.task_done()
            return
        self._active.add(asset_id)
        try:
            graph = build_asset_graph(self)
            state: AssetPipelineState = {"asset_id": str(asset_id), "error": None}
            await graph.ainvoke(state)
        except Exception as exc:
            logger.exception("Pipeline failed for %s", asset_id)
            async with get_session() as session:
                await AssetRepo(session).mark_failed(asset_id, str(exc))
            await self._emit(
                asset_id,
                PipelineEventType.STEP_FAILED,
                step="pipeline",
                message=str(exc),
            )
            await self._event_bus.publish(
                str(asset_id),
                {"type": "error", "asset_id": str(asset_id), "message": str(exc)},
            )
        finally:
            self._active.discard(asset_id)
            self._queue.task_done()

    async def node_parse(self, state: AssetPipelineState) -> dict[str, Any]:
        asset_id = uuid.UUID(state["asset_id"])
        async with self._parse_sem:
            await self._emit(
                asset_id,
                PipelineEventType.STEP_START,
                step="parse",
                to_status=AssetStatus.RECOGNIZING,
            )
            await self._set_status(asset_id, AssetStatus.RECOGNIZING)
            async with get_session() as session:
                asset = await AssetRepo(session).get_by_id(asset_id)
            if asset is None:
                return {"error": f"Asset not found: {asset_id}"}
            try:
                if asset.modality in (AssetModality.VIDEO, AssetModality.AUDIO):
                    async with self._whisper_sem:
                        action, processed_rel = await asyncio.to_thread(_run_parse_sync, asset)
                else:
                    action, processed_rel = await asyncio.to_thread(_run_parse_sync, asset)
                async with get_session() as session:
                    await AssetRepo(session).update_processed_path(
                        asset_id,
                        processed_rel,
                    )
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_COMPLETE,
                    step="parse",
                    metadata={"action": action, "processed_path": processed_rel},
                )
                return {
                    "processed_path": processed_rel,
                    "modality": asset.modality.value,
                    "raw_path": asset.raw_path,
                    "parse_action": action,
                    "step": "parse",
                    "error": None,
                }
            except Exception as exc:
                await self._set_status(asset_id, AssetStatus.FAILED)
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_FAILED,
                    step="parse",
                    message=str(exc),
                )
                return {"error": str(exc), "step": "parse"}

    async def node_outline(self, state: AssetPipelineState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        asset_id = uuid.UUID(state["asset_id"])
        processed_path = state.get("processed_path")
        if not processed_path:
            return {"error": "missing processed_path after parse", "step": "outline"}

        async with self._outline_sem:
            await self._emit(
                asset_id,
                PipelineEventType.STEP_START,
                step="outline",
                to_status=AssetStatus.STRUCTURING,
            )
            await self._set_status(asset_id, AssetStatus.STRUCTURING)
            try:
                summary = await generate_outline_for_processed_dir(
                    PROJECT_ROOT / processed_path,
                    asset_id=asset_id,
                )
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_COMPLETE,
                    step="outline",
                    metadata=summary,
                )
                return {"outline_action": summary.get("action"), "step": "outline", "error": None}
            except Exception as exc:
                await self._set_status(asset_id, AssetStatus.FAILED)
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_FAILED,
                    step="outline",
                    message=str(exc),
                )
                return {"error": str(exc), "step": "outline"}

    async def node_ingest(self, state: AssetPipelineState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        asset_id = uuid.UUID(state["asset_id"])
        processed_path = state.get("processed_path")
        if not processed_path:
            return {"error": "missing processed_path after parse", "step": "ingest"}

        async with self._ingest_sem:
            await self._emit(
                asset_id,
                PipelineEventType.STEP_START,
                step="ingest",
                to_status=AssetStatus.INGESTING,
            )
            await self._set_status(asset_id, AssetStatus.INGESTING)
            try:
                summary = await ingest_processed_dir(
                    PROJECT_ROOT / processed_path,
                    asset_id=asset_id,
                )
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_COMPLETE,
                    step="ingest",
                    metadata=summary,
                )
                await self._set_status(asset_id, AssetStatus.READY)
                await self._emit(
                    asset_id,
                    PipelineEventType.STATUS_CHANGE,
                    step="ingest",
                    to_status=AssetStatus.READY,
                )
                await self._event_bus.publish(
                    str(asset_id),
                    {"type": "completed", "asset_id": str(asset_id), "status": "ready"},
                )
                return {"ingest_action": summary.get("action"), "step": "ingest", "error": None}
            except Exception as exc:
                await self._set_status(asset_id, AssetStatus.FAILED)
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_FAILED,
                    step="ingest",
                    message=str(exc),
                )
                return {"error": str(exc), "step": "ingest"}

    async def node_kg_extract(self, state: AssetPipelineState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        asset_id = uuid.UUID(state["asset_id"])
        kg_cfg = load_kg_config()
        if not kg_cfg.get("enabled", True):
            async with get_session() as session:
                await AssetRepo(session).update_kg_status(asset_id, KgStatus.SKIPPED)
            return {"kg_action": "skipped", "step": "kg_extract", "error": None}

        fail_open = bool(kg_cfg.get("fail_open", True))
        async with self._kg_sem:
            await self._emit(
                asset_id,
                PipelineEventType.STEP_START,
                step="kg_extract",
                to_status=AssetStatus.KG_EXTRACTING,
            )
            await self._set_status(asset_id, AssetStatus.KG_EXTRACTING)
            async with get_session() as session:
                await AssetRepo(session).update_kg_status(asset_id, KgStatus.EXTRACTING)
            try:
                summary = await asyncio.to_thread(extract_kg_for_asset_sync, asset_id)
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_COMPLETE,
                    step="kg_extract",
                    metadata=summary,
                )
                await self._set_status(asset_id, AssetStatus.READY)
                return {"kg_action": summary.get("action"), "step": "kg_extract", "error": None}
            except Exception as exc:
                async with get_session() as session:
                    await AssetRepo(session).update_kg_status(asset_id, KgStatus.FAILED)
                await self._emit(
                    asset_id,
                    PipelineEventType.STEP_FAILED,
                    step="kg_extract",
                    message=str(exc),
                )
                if fail_open:
                    await self._set_status(asset_id, AssetStatus.READY)
                    return {"kg_action": "failed", "step": "kg_extract", "error": None}
                await self._set_status(asset_id, AssetStatus.FAILED)
                return {"error": str(exc), "step": "kg_extract"}

    async def node_mark_failed(self, state: AssetPipelineState) -> dict[str, Any]:
        asset_id = uuid.UUID(state["asset_id"])
        message = state.get("error") or "pipeline failed"
        async with get_session() as session:
            await AssetRepo(session).mark_failed(asset_id, message)
        await self._event_bus.publish(
            str(asset_id),
            {"type": "error", "asset_id": str(asset_id), "message": message},
        )
        return {"step": "failed"}


def _route_on_error(state: AssetPipelineState) -> str:
    return "mark_failed" if state.get("error") else "continue"


def build_asset_graph(manager: AssetsManager):
    graph = StateGraph(AssetPipelineState)
    graph.add_node("parse", manager.node_parse)
    graph.add_node("outline", manager.node_outline)
    graph.add_node("ingest", manager.node_ingest)
    graph.add_node("kg_extract", manager.node_kg_extract)
    graph.add_node("mark_failed", manager.node_mark_failed)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges(
        "parse",
        _route_on_error,
        {"continue": "outline", "mark_failed": "mark_failed"},
    )
    graph.add_conditional_edges(
        "outline",
        _route_on_error,
        {"continue": "ingest", "mark_failed": "mark_failed"},
    )
    graph.add_conditional_edges(
        "ingest",
        _route_on_error,
        {"continue": "kg_extract", "mark_failed": "mark_failed"},
    )
    graph.add_conditional_edges(
        "kg_extract",
        _route_on_error,
        {"continue": END, "mark_failed": "mark_failed"},
    )
    graph.add_edge("mark_failed", END)
    return graph.compile()


def get_assets_manager() -> AssetsManager:
    return AssetsManager()


async def create_asset_for_upload(
    *,
    name: str,
    modality: AssetModality,
    raw_path: str,
    file_size_bytes: int | None = None,
) -> AssetRead:
    async with get_session() as session:
        asset = await AssetRepo(session).create(
            AssetCreate(
                name=name,
                modality=modality,
                raw_path=raw_path,
                file_size_bytes=file_size_bytes,
                status=AssetStatus.RAW,
            )
        )
        return asset


def _extension_modality(filename: str) -> AssetModality | None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return AssetModality.PDF
    if ext in {".mp4", ".mkv", ".mov", ".webm", ".avi"}:
        return AssetModality.VIDEO
    if ext in {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}:
        return AssetModality.AUDIO
    return None


def _raw_dir_for_modality(modality: AssetModality) -> Path:
    return _MODALITY_RAW_DIRS[modality]


async def _cli_run(asset_id: uuid.UUID | None, raw_path: Path | None) -> int:
    manager = get_assets_manager()
    await manager.start()
    try:
        if asset_id is not None:
            await manager.enqueue(asset_id)
        elif raw_path is not None:
            modality = _extension_modality(raw_path.name)
            if modality is None:
                print(f"Unsupported file type: {raw_path}")
                return 1
            rel = relative_path(raw_path, PROJECT_ROOT)
            asset = await create_asset_for_upload(
                name=raw_path.name,
                modality=modality,
                raw_path=rel,
                file_size_bytes=raw_path.stat().st_size,
            )
            await manager.enqueue(asset.id)
            asset_id = asset.id
        else:
            print("Provide --asset-id or --raw-path")
            return 1

        while asset_id in manager._active or not manager._queue.empty():
            await asyncio.sleep(0.5)
            async with get_session() as session:
                current = await AssetRepo(session).get_by_id(asset_id)
            if current and current.status in {AssetStatus.READY, AssetStatus.FAILED}:
                if asset_id not in manager._active:
                    break

        async with get_session() as session:
            final = await AssetRepo(session).get_by_id(asset_id)
        print(json.dumps({"asset_id": str(asset_id), "status": final.status.value if final else None}, ensure_ascii=False))
        return 0 if final and final.status == AssetStatus.READY else 1
    finally:
        await manager.stop()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - [AssetsManager] - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Run asset pipeline for one asset")
    parser.add_argument("--asset-id", type=uuid.UUID, default=None)
    parser.add_argument("--raw-path", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_cli_run(args.asset_id, args.raw_path))


if __name__ == "__main__":
    sys.exit(main())
