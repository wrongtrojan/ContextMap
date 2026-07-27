"""Live E2E: real DeepSeek + PostgreSQL retrieval + reranker (no mocks)."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from unittest.mock import AsyncMock

from core.assets_manager import AssetsManager, get_assets_manager
from core.chats_manager import ChatsManager, get_chats_manager
from database.enums import AssetStatus, ChatStatus, ChatTurnEventType
from database.models import Asset, ContentUnit
from database.repositories import ChatSessionRepo
from database.session import dispose_engine, get_session
from services.outline.llm import resolve_api_key
from services.retrieval.config import load_llm_config
from tests.helpers.env import deepseek_api_key_available, load_dotenv
from tests.helpers.live_progress import LiveProgressTracker, parse_sse_lines
from tests.test_chats_e2e import _sync_chat_manager_singleton
from web.main import app

MIN_READY_ASSETS = 3
LIVE_TIMEOUT_SEC = 900.0
LIVE_QUERY = "Explain virtual memory and page tables in operating systems."


def _live_infer_enabled() -> bool:
    return os.getenv("LIVE_ENABLE_INFER", "").lower() in {"1", "true", "yes"}


async def _corpus_ready() -> tuple[bool, str]:
    async with get_session() as session:
        ready = await session.scalar(
            select(func.count()).select_from(Asset).where(Asset.status == AssetStatus.READY)
        )
        units = await session.scalar(select(func.count()).select_from(ContentUnit))
    if (ready or 0) < MIN_READY_ASSETS:
        return False, f"need >= {MIN_READY_ASSETS} READY assets, got {ready}"
    if (units or 0) < 50:
        return False, f"need >= 50 content units, got {units}"
    return True, ""


async def _warmup_models(progress: LiveProgressTracker) -> None:
    from services.evaluate.rerank import rerank_scores
    from services.infer.config import load_infer_config
    from services.ingest.embed import embed_texts

    progress._log("warming up BGE-M3 embedding model…")
    await asyncio.to_thread(embed_texts, ["warmup query for live e2e"])
    progress._log("warming up BGE reranker…")
    await asyncio.to_thread(rerank_scores, "warmup", ["warmup passage"])

    infer_cfg = load_infer_config()
    visual_on = bool((infer_cfg.get("visual") or {}).get("enabled", True))
    sandbox_on = bool((infer_cfg.get("sandbox") or {}).get("enabled", True))
    progress._log(f"model warmup done (infer visual={visual_on} sandbox={sandbox_on})")


async def _wait_for_idle_live(
    session_id: str,
    progress: LiveProgressTracker,
    *,
    timeout: float = LIVE_TIMEOUT_SEC,
) -> dict:
    manager = get_chats_manager()
    session_uuid = uuid.UUID(session_id)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        detail = await manager.get_session_detail(session_uuid)
        assert detail is not None
        progress.on_poll_detail(detail)
        if session_uuid in manager._active_turns:
            break
        if detail["status"] != ChatStatus.IDLE.value:
            break
        if detail["status"] == ChatStatus.IDLE.value and len(detail["messages"]) >= 2:
            progress.print_summary()
            return detail
        progress.maybe_heartbeat()
        await asyncio.sleep(0.1)
    else:
        progress.print_summary()
        pytest.fail(f"Timed out waiting for turn to start on session {session_id}")

    while loop.time() < deadline:
        detail = await manager.get_session_detail(session_uuid)
        assert detail is not None
        progress.on_poll_detail(detail)
        progress.maybe_heartbeat()
        if session_uuid not in manager._active_turns:
            if detail["status"] == ChatStatus.FAILED.value:
                progress.print_summary()
                pytest.fail(f"Chat turn failed: {detail}")
            if detail["status"] == ChatStatus.IDLE.value and len(detail["messages"]) >= 2:
                progress.print_summary()
                return detail
        await asyncio.sleep(0.25)

    detail = await manager.get_session_detail(session_uuid)
    progress.print_summary()
    pytest.fail(f"Timed out waiting for session {session_id} to finish: {detail}")


@pytest.fixture
async def live_api_client(monkeypatch):
    load_dotenv()
    if not deepseek_api_key_available():
        pytest.skip("DEEPSEEK_API_KEY not set in .env")
    ok, reason = await _corpus_ready()
    if not ok:
        pytest.skip(reason)

    if not _live_infer_enabled():
        original_load = __import__(
            "services.infer.config", fromlist=["load_infer_config"]
        ).load_infer_config

        def _load_infer_config_without_optional(*args, **kwargs):
            cfg = original_load(*args, **kwargs)
            cfg = dict(cfg)
            cfg["visual"] = {**(cfg.get("visual") or {}), "enabled": False}
            cfg["sandbox"] = {**(cfg.get("sandbox") or {}), "enabled": False}
            return cfg

        monkeypatch.setattr(
            "services.infer.config.load_infer_config",
            _load_infer_config_without_optional,
        )

    manager = get_assets_manager()
    original_start = manager.start
    original_stop = manager.stop
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    ChatsManager._instance = None
    _sync_chat_manager_singleton()

    progress = LiveProgressTracker()
    if _live_infer_enabled():
        progress._log("LIVE_ENABLE_INFER=1 → visual/sandbox enabled for this run")
    else:
        progress._log("infer visual/sandbox disabled (set LIVE_ENABLE_INFER=1 to include)")
    await _warmup_models(progress)

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test", timeout=LIVE_TIMEOUT_SEC) as client:
            client._live_progress = progress  # type: ignore[attr-defined]
            yield client

    manager.start = original_start
    manager.stop = original_stop
    AssetsManager._instance = None
    ChatsManager._instance = None
    await dispose_engine()


async def _cleanup_session(session_id: uuid.UUID) -> None:
    async with get_session() as session:
        await ChatSessionRepo(session).delete(session_id)


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_chat_full_turn_api(live_api_client: AsyncClient):
    """Real LLM + hybrid search + rerank + synthesize through HTTP API."""
    progress: LiveProgressTracker = live_api_client._live_progress  # type: ignore[attr-defined]

    create = await live_api_client.post("/api/v1/chats/sessions")
    assert create.status_code == 200
    session_id = create.json()["session_id"]
    progress._log(f"session_id={session_id}")

    seen_events: list[str] = []
    finished = asyncio.Event()
    poll_done = asyncio.Event()
    poll_detail: dict | None = None

    async def _poll_until_idle() -> None:
        nonlocal poll_detail
        manager = get_chats_manager()
        session_uuid = uuid.UUID(session_id)
        deadline = asyncio.get_event_loop().time() + LIVE_TIMEOUT_SEC
        while asyncio.get_event_loop().time() < deadline:
            detail = await manager.get_session_detail(session_uuid)
            assert detail is not None
            progress.on_poll_detail(detail)
            if detail["status"] == ChatStatus.IDLE.value and len(detail["messages"]) >= 2:
                poll_detail = detail
                poll_done.set()
                return
            progress.maybe_heartbeat()
            await asyncio.sleep(0.25)
        progress.print_summary()
        pytest.fail("Timed out waiting for poll idle + assistant message")

    async def _collect_sse() -> None:
        data_buffer: list[str] = []
        async with live_api_client.stream(
            "GET",
            "/api/v1/chats/stream",
            params={"session_id": session_id},
            timeout=LIVE_TIMEOUT_SEC,
        ) as stream:
            async for line in stream.aiter_lines():
                payload = parse_sse_lines(line, data_buffer=data_buffer)
                if payload is None:
                    continue
                seen_events.append(str(payload.get("type") or ""))
                if progress.on_sse_payload(payload):
                    finished.set()
                    return
                progress.maybe_heartbeat()

    collector = asyncio.create_task(_collect_sse())
    poller = asyncio.create_task(_poll_until_idle())
    await asyncio.sleep(0.05)

    progress._log(f"POST turn query={LIVE_QUERY!r}")
    turn = await live_api_client.post(
        f"/api/v1/chats/sessions/{session_id}/turns",
        json={"message": LIVE_QUERY},
    )
    assert turn.status_code == 200, turn.text
    progress._log("turn accepted, streaming progress via SSE + poll fallback…")

    sse_wait = asyncio.create_task(finished.wait())
    poll_wait = asyncio.create_task(poll_done.wait())
    done, pending = await asyncio.wait(
        {sse_wait, poll_wait},
        return_when=asyncio.FIRST_COMPLETED,
        timeout=LIVE_TIMEOUT_SEC,
    )
    for task in pending:
        task.cancel()
    if not done:
        progress.print_summary()
        pytest.fail("Timed out waiting for SSE completed/error or poll idle completion")

    for task in (collector, poller):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    if poll_detail is None:
        detail = await _wait_for_idle_live(session_id, progress, timeout=60.0)
    else:
        detail = poll_detail
        progress.print_summary()

    assert detail["status"] == ChatStatus.IDLE.value, detail
    assert len(detail["messages"]) == 2
    assistant = detail["messages"][1]["content"]
    assert len(assistant) > 80, f"assistant reply too short: {assistant[:200]!r}"
    assert detail["evidences"], "expected retrieved evidence persisted"
    assert any(item["type"] == ChatTurnEventType.EVALUATION.value for item in detail["events"])
    assert any(item["type"] == ChatTurnEventType.COMPLETED.value for item in detail["events"])
    assert not any(item["type"] == ChatTurnEventType.TOKEN.value for item in detail["events"])
    assert "completed" in seen_events or poll_detail is not None

    progress._log("--- Live E2E PASSED ---")
    progress._log(f"evidence_count={len(detail['evidences'])}")
    progress._log(f"assistant_preview={assistant[:400]}…")

    await _cleanup_session(uuid.UUID(session_id))


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_deepseek_api_key_resolves():
    load_dotenv()
    if not deepseek_api_key_available():
        pytest.skip("DEEPSEEK_API_KEY not set")
    key = resolve_api_key(load_llm_config())
    assert key
