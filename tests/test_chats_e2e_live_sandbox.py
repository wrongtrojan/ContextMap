"""Live E2E: verify sandbox infer enters the chat chain."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from core.assets_manager import AssetsManager, get_assets_manager
from core.chats_manager import ChatsManager, get_chats_manager
from database.enums import ChatStatus, ChatTurnEventType
from database.repositories import ChatSessionRepo
from database.session import dispose_engine
from tests.helpers.env import deepseek_api_key_available, load_dotenv
from tests.helpers.live_progress import LiveProgressTracker, parse_sse_lines
from tests.test_chats_e2e import _sync_chat_manager_singleton
from tests.test_chats_e2e_live import (
    LIVE_TIMEOUT_SEC,
    _cleanup_session,
    _corpus_ready,
    _wait_for_idle_live,
    _warmup_models,
)
from web.main import app

SANDBOX_QUERY = "请计算并验证：2的10次方等于多少？"


@pytest.fixture
async def live_sandbox_client(monkeypatch):
    load_dotenv()
    if not deepseek_api_key_available():
        pytest.skip("DEEPSEEK_API_KEY not set in .env")
    ok, reason = await _corpus_ready()
    if not ok:
        pytest.skip(reason)

    infer_config_mod = __import__("services.infer.config", fromlist=["load_infer_config"])
    original_load = infer_config_mod.load_infer_config

    def _sandbox_only_config(*args, **kwargs):
        cfg = dict(original_load(*args, **kwargs))
        cfg["visual"] = {**(cfg.get("visual") or {}), "enabled": False}
        cfg["sandbox"] = {**(cfg.get("sandbox") or {}), "enabled": True}
        return cfg

    monkeypatch.setattr("services.infer.config.load_infer_config", _sandbox_only_config)

    manager = get_assets_manager()
    original_start = manager.start
    original_stop = manager.stop
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    ChatsManager._instance = None
    _sync_chat_manager_singleton()

    progress = LiveProgressTracker(label="live-sandbox")
    progress._log("sandbox enabled, visual disabled for this run")
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


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_chat_sandbox_infer_in_chain(live_sandbox_client: AsyncClient):
    """Sandbox subprocess + LLM prep should run when query hits sandbox keywords."""
    progress: LiveProgressTracker = live_sandbox_client._live_progress  # type: ignore[attr-defined]

    create = await live_sandbox_client.post("/api/v1/chats/sessions")
    assert create.status_code == 200
    session_id = create.json()["session_id"]
    progress._log(f"session_id={session_id}")

    finished = asyncio.Event()
    poll_done = asyncio.Event()
    poll_detail: dict | None = None
    sandbox_sse: list[dict] = []

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
        async with live_sandbox_client.stream(
            "GET",
            "/api/v1/chats/stream",
            params={"session_id": session_id},
            timeout=LIVE_TIMEOUT_SEC,
        ) as stream:
            async for line in stream.aiter_lines():
                payload = parse_sse_lines(line, data_buffer=data_buffer)
                if payload is None:
                    continue
                if payload.get("type") == "infer_result" and payload.get("kind") == "sandbox":
                    sandbox_sse.append(payload)
                if progress.on_sse_payload(payload):
                    finished.set()
                    return
                progress.maybe_heartbeat()

    collector = asyncio.create_task(_collect_sse())
    poller = asyncio.create_task(_poll_until_idle())
    await asyncio.sleep(0.05)

    progress._log(f"POST turn query={SANDBOX_QUERY!r}")
    turn = await live_sandbox_client.post(
        f"/api/v1/chats/sessions/{session_id}/turns",
        json={"message": SANDBOX_QUERY},
    )
    assert turn.status_code == 200, turn.text

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
        pytest.fail("Timed out waiting for turn completion")

    for task in (collector, poller):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    detail = poll_detail or await _wait_for_idle_live(session_id, progress, timeout=60.0)
    progress.print_summary()

    sandbox_events = [
        item
        for item in detail["events"]
        if item["type"] == ChatTurnEventType.INFER_RESULT.value
        and any(r.get("kind") == "sandbox" for r in (item.get("detail") or {}).get("results") or [])
    ]
    assert sandbox_sse or sandbox_events, (
        "expected sandbox infer_result in SSE or persisted events; "
        f"infer events={[e for e in detail['events'] if e['type']==ChatTurnEventType.INFER_RESULT.value]}"
    )

    sandbox_content = ""
    if sandbox_sse:
        sandbox_content = str(sandbox_sse[0].get("summary") or "")
    else:
        results = (sandbox_events[0].get("detail") or {}).get("results") or []
        sandbox_content = str(next(r["content"] for r in results if r.get("kind") == "sandbox"))

    progress._log(f"sandbox_result={sandbox_content[:200]!r}")
    assert "1024" in sandbox_content or sandbox_content.isdigit(), sandbox_content
    assert not sandbox_content.startswith("[sandbox failed")
    assert not sandbox_content.startswith("[sandbox unavailable")

    progress._log("--- Live sandbox chain PASSED ---")
    await _cleanup_session(uuid.UUID(session_id))
