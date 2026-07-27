"""End-to-end tests for chat API, manager orchestration, SSE, and PG persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.assets_manager import AssetsManager, get_assets_manager
from core.chats_manager import ChatsManager, get_chats_manager
from database.enums import ChatStatus, ChatTurnEventType, MessageRole
from database.repositories import ChatSessionRepo
from database.session import dispose_engine, get_session
from services.evaluate.types import EvaluationReport, RefetchHint
from services.infer.types import InferResult
from web.api.v1 import chats as chats_api
from web.api.v1 import status as status_api
from web.main import app


def _sync_chat_manager_singleton() -> None:
    manager = get_chats_manager()
    chats_api.chats_manager = manager
    status_api.chats_manager = manager


def _sample_search_needs() -> dict[str, Any]:
    return {
        "search_params": {
            "keywords": ["virtual", "memory"],
            "semantic_query": "virtual memory page table",
            "top_k": 8,
        },
        "preferences": {"modality": None},
    }


def _sample_evidence() -> list[dict[str, Any]]:
    return [
        {
            "content": "Virtual memory uses page tables to map virtual addresses.",
            "score": 0.92,
            "rerank_score": 0.91,
            "metadata": {"asset_name": "CSAPP", "modality": "video", "type": "transcript"},
            "source": "hybrid",
        },
        {
            "content": "Page faults trigger kernel handling of missing pages.",
            "score": 0.81,
            "rerank_score": 0.80,
            "metadata": {"asset_name": "CSAPP", "modality": "video", "type": "transcript"},
            "source": "hybrid",
        },
    ]


def _proceed_report(evidence: list[dict[str, Any]] | None = None) -> EvaluationReport:
    items = evidence or _sample_evidence()
    return EvaluationReport(
        recommendation="proceed",
        confidence=0.88,
        evidence=items,
        scores=[],
    )


def _refetch_report() -> EvaluationReport:
    return EvaluationReport(
        recommendation="refetch",
        confidence=0.35,
        evidence=_sample_evidence()[:1],
        scores=[],
        refetch_hint=RefetchHint(append_keywords=["page", "table"]),
    )


async def _mock_stream_chat_completion(_prompt: str) -> AsyncIterator[str]:
    for token in ["Virtual ", "memory ", "maps ", "pages."]:
        yield token


@asynccontextmanager
async def _chat_e2e_patches(
    *,
    evaluate_side_effect: Callable[..., EvaluationReport] | None = None,
):
    evaluate_fn = evaluate_side_effect or (lambda **_: _proceed_report())

    async def _refine_query(_context: str) -> dict[str, Any]:
        return _sample_search_needs()

    async def _hybrid_search(_db, *, search_needs: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "results": _sample_evidence(),
            "debug": {"keywords": search_needs.get("search_params", {}).get("keywords", [])},
        }

    async def _evaluate_evidence(**kwargs: Any) -> EvaluationReport:
        return evaluate_fn(**kwargs)

    async def _run_infer(**_kwargs: Any) -> list[InferResult]:
        return [
            InferResult(
                kind="sandbox",
                content="sandbox: page table walk simulated",
                source_expression="1+1",
            )
        ]

    async def _expand_linked_media(_db, evidence, *, window_sec: float = 2.0):
        return evidence

    patches = [
        patch("core.chats_graph.refine_query", new=AsyncMock(side_effect=_refine_query)),
        patch("core.chats_graph.hybrid_search", new=AsyncMock(side_effect=_hybrid_search)),
        patch("core.chats_graph.evaluate_evidence", new=AsyncMock(side_effect=_evaluate_evidence)),
        patch("core.chats_graph.expand_linked_media", new=AsyncMock(side_effect=_expand_linked_media)),
        patch("core.chats_graph.run_infer", new=AsyncMock(side_effect=_run_infer)),
        patch("core.chats_manager.stream_chat_completion", side_effect=_mock_stream_chat_completion),
    ]
    for item in patches:
        item.start()
    try:
        yield
    finally:
        for item in patches:
            item.stop()


@pytest.fixture(autouse=True)
async def reset_chats_manager():
    """Isolate ChatsManager singleton between tests."""
    ChatsManager._instance = None
    _sync_chat_manager_singleton()
    yield
    manager = get_chats_manager()
    for task in list(manager._turn_tasks.values()):
        task.cancel()
    manager._turn_tasks.clear()
    manager._active_turns.clear()
    ChatsManager._instance = None
    await dispose_engine()


@pytest.fixture
async def api_client():
    manager = get_assets_manager()
    original_start = manager.start
    original_stop = manager.stop
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    _sync_chat_manager_singleton()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    manager.start = original_start
    manager.stop = original_stop
    AssetsManager._instance = None
    await dispose_engine()


async def _wait_for_idle(session_id: str, *, timeout: float = 15.0) -> dict[str, Any]:
    manager = get_chats_manager()
    session_uuid = uuid.UUID(session_id)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    # Wait until the turn actually starts (session leaves idle or task is tracked).
    while loop.time() < deadline:
        detail = await manager.get_session_detail(session_uuid)
        assert detail is not None
        if session_uuid in manager._active_turns:
            break
        if detail["status"] != ChatStatus.IDLE.value:
            break
        if detail["status"] == ChatStatus.IDLE.value and len(detail["messages"]) >= 2:
            return detail
        await asyncio.sleep(0.05)
    else:
        pytest.fail(f"Timed out waiting for turn to start on session {session_id}")

    # Wait until the turn finishes and assistant message is persisted.
    while loop.time() < deadline:
        if session_uuid not in manager._active_turns:
            detail = await manager.get_session_detail(session_uuid)
            assert detail is not None
            if detail["status"] == ChatStatus.FAILED.value:
                pytest.fail(f"Chat turn failed: {detail}")
            if detail["status"] == ChatStatus.IDLE.value and len(detail["messages"]) >= 2:
                return detail
        await asyncio.sleep(0.15)
    detail = await manager.get_session_detail(session_uuid)
    pytest.fail(f"Timed out waiting for session {session_id} to finish: {detail}")


async def _cleanup_session(session_id: uuid.UUID) -> None:
    async with get_session() as session:
        await ChatSessionRepo(session).delete(session_id)


@pytest.mark.asyncio
async def test_api_create_session(api_client: AsyncClient):
    resp = await api_client.post("/api/v1/chats/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["chat_status"] == ChatStatus.IDLE.value
    assert body["external_id"].startswith("CH-")
    session_id = uuid.UUID(body["session_id"])

    status = await api_client.get("/api/v1/status/single_chat", params={"session_id": body["session_id"]})
    assert status.status_code == 200
    detail = status.json()["data"]
    assert detail["messages"] == []
    assert detail["evidences"] == []

    await _cleanup_session(session_id)


@pytest.mark.asyncio
async def test_api_full_turn_persists_messages_evidence_and_events(api_client: AsyncClient):
    async with _chat_e2e_patches():
        create = await api_client.post("/api/v1/chats/sessions")
        session_id = create.json()["session_id"]
        user_message = "Explain virtual memory page tables"

        turn = await api_client.post(
            f"/api/v1/chats/sessions/{session_id}/turns",
            json={"message": user_message},
        )
        assert turn.status_code == 200
        assert turn.json()["turn_seq"] == 1

        detail = await _wait_for_idle(session_id)

        assert detail["status"] == ChatStatus.IDLE.value
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == MessageRole.USER.value
        assert detail["messages"][0]["content"] == user_message
        assert detail["messages"][1]["role"] == MessageRole.ASSISTANT.value
        assert "Virtual memory maps pages." in detail["messages"][1]["content"]

        assert detail["evidences"]
        assert detail["events"]
        event_types = {item["type"] for item in detail["events"]}
        assert ChatTurnEventType.STEP_START.value in event_types
        assert ChatTurnEventType.EVALUATION.value in event_types
        assert ChatTurnEventType.EVIDENCE_SNAPSHOT.value in event_types
        assert ChatTurnEventType.INFER_RESULT.value in event_types
        assert ChatTurnEventType.COMPLETED.value in event_types
        assert ChatTurnEventType.TOKEN.value not in event_types

        await _cleanup_session(uuid.UUID(session_id))


@pytest.mark.asyncio
async def test_api_sse_stream_receives_lifecycle_events(api_client: AsyncClient):
    async with _chat_e2e_patches():
        create = await api_client.post("/api/v1/chats/sessions")
        session_id = create.json()["session_id"]
        seen_types: list[str] = []

        async def _collect_stream() -> None:
            async with api_client.stream(
                "GET",
                "/api/v1/chats/stream",
                params={"session_id": session_id},
                timeout=20.0,
            ) as stream:
                assert stream.status_code == 200
                async for line in stream.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = json.loads(line.removeprefix("data:").strip())
                    seen_types.append(payload.get("type", ""))
                    if payload.get("type") in {"completed", "error"}:
                        return

        collector = asyncio.create_task(_collect_stream())
        await asyncio.sleep(0.05)
        turn_resp = await api_client.post(
            f"/api/v1/chats/sessions/{session_id}/turns",
            json={"message": "What is a page table?"},
        )
        assert turn_resp.status_code == 200
        await asyncio.wait_for(collector, timeout=20.0)

        assert seen_types
        assert "completed" in seen_types
        await _cleanup_session(uuid.UUID(session_id))


@pytest.mark.asyncio
async def test_api_duplicate_turn_returns_409(api_client: AsyncClient):
    gate = asyncio.Event()

    async def _slow_synthesize(_state, _manager):
        await gate.wait()
        return {"answer": "blocked"}

    async with _chat_e2e_patches():
        create = await api_client.post("/api/v1/chats/sessions")
        session_id = create.json()["session_id"]

        with patch("core.chats_graph.node_synthesize", new=AsyncMock(side_effect=_slow_synthesize)):
            first = asyncio.create_task(
                api_client.post(
                    f"/api/v1/chats/sessions/{session_id}/turns",
                    json={"message": "first turn"},
                )
            )
            await asyncio.sleep(0.3)

            second = await api_client.post(
                f"/api/v1/chats/sessions/{session_id}/turns",
                json={"message": "second turn"},
            )
            assert second.status_code == 409

            gate.set()
            await first

        await _wait_for_idle(session_id)
        await _cleanup_session(uuid.UUID(session_id))


@pytest.mark.asyncio
async def test_api_unknown_session_turn_returns_404(api_client: AsyncClient):
    missing = uuid.uuid4()
    resp = await api_client.post(
        f"/api/v1/chats/sessions/{missing}/turns",
        json={"message": "hello"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manager_refetch_loop_then_complete():
    calls = {"evaluate": 0}

    def _evaluate_side_effect(**_kwargs: Any) -> EvaluationReport:
        calls["evaluate"] += 1
        if calls["evaluate"] == 1:
            return _refetch_report()
        return _proceed_report()

    async with _chat_e2e_patches(evaluate_side_effect=_evaluate_side_effect):
        manager = get_chats_manager()
        _sync_chat_manager_singleton()
        session = await manager.create_session(chat_name="Refetch E2E")
        try:
            turn_seq = await manager.start_turn(session.id, "Explain page tables in detail")
            assert turn_seq == 1

            detail = await _wait_for_idle(str(session.id), timeout=20.0)
            assert calls["evaluate"] >= 2
            assert detail["status"] == ChatStatus.IDLE.value
            assert any(item["type"] == ChatTurnEventType.REFETCH.value for item in detail["events"])
            assert detail["messages"][-1]["content"]
        finally:
            await _cleanup_session(session.id)


@pytest.mark.asyncio
async def test_global_chat_status_reflects_sessions(api_client: AsyncClient):
    async with _chat_e2e_patches():
        create = await api_client.post("/api/v1/chats/sessions")
        session_id = uuid.UUID(create.json()["session_id"])
        try:
            await api_client.post(
                f"/api/v1/chats/sessions/{session_id}/turns",
                json={"message": "heap allocation basics"},
            )
            await _wait_for_idle(str(session_id))

            global_resp = await api_client.get("/api/v1/status/global_chats")
            assert global_resp.status_code == 200
            data = global_resp.json()["data"]
            assert data["chats_number"] >= 1
            assert data["active_turns"] == 0

            detail_resp = await api_client.get(
                "/api/v1/status/single_chat",
                params={"session_id": str(session_id)},
            )
            assert detail_resp.json()["data"]["status"] == ChatStatus.IDLE.value
        finally:
            await _cleanup_session(session_id)
