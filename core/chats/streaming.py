"""SSE token batching and event bus with milestone-safe delivery."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Subscriber:
    """One SSE consumer: milestone queue + coalesced token buffer."""

    milestones: asyncio.Queue[dict[str, Any]]
    token_buffer: str = ""
    token_updated_at: float = field(default_factory=time.monotonic)
    _token_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatEventBus:
    """In-process pub/sub for chat SSE streams."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[_Subscriber]] = defaultdict(list)
        self._registry_lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> _Subscriber:
        sub = _Subscriber(milestones=asyncio.Queue())
        async with self._registry_lock:
            self._subscribers[session_id].append(sub)
        return sub

    async def unsubscribe(self, session_id: str, sub: _Subscriber) -> None:
        async with self._registry_lock:
            subs = self._subscribers.get(session_id, [])
            if sub in subs:
                subs.remove(sub)

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "message")
        async with self._registry_lock:
            subs = list(self._subscribers.get(session_id, []))

        if event_type == "token":
            content = str(event.get("content") or "")
            if not content or not subs:
                return
            for sub in subs:
                async with sub._token_lock:
                    sub.token_buffer += content
                    sub.token_updated_at = time.monotonic()
            return

        payload = dict(event)
        for sub in subs:
            await sub.milestones.put(payload)

    async def flush_token_buffers(
        self,
        session_id: str,
        *,
        force: bool = False,
        batch_ms: float = 50.0,
        batch_chars: int = 256,
    ) -> None:
        now = time.monotonic()
        async with self._registry_lock:
            subs = list(self._subscribers.get(session_id, []))

        for sub in subs:
            async with sub._token_lock:
                if not sub.token_buffer:
                    continue
                elapsed_ms = (now - sub.token_updated_at) * 1000
                if not force and len(sub.token_buffer) < batch_chars and elapsed_ms < batch_ms:
                    continue
                text = sub.token_buffer
                sub.token_buffer = ""
                sub.token_updated_at = now
            if text:
                await sub.milestones.put({"type": "token", "content": text})


class TokenStreamPublisher:
    """Accumulate synthesize tokens and publish in batches."""

    def __init__(
        self,
        bus: ChatEventBus,
        session_id: str,
        *,
        batch_ms: float = 50.0,
        batch_chars: int = 256,
    ) -> None:
        self._bus = bus
        self._session_id = session_id
        self._batch_ms = batch_ms
        self._batch_chars = batch_chars
        self._buffer = ""
        self._last_flush = time.monotonic()

    async def append(self, token: str) -> None:
        if not token:
            return
        self._buffer += token
        now = time.monotonic()
        if len(self._buffer) >= self._batch_chars or (now - self._last_flush) * 1000 >= self._batch_ms:
            await self._flush()

    async def flush(self) -> None:
        await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return
        chunk = self._buffer
        self._buffer = ""
        self._last_flush = time.monotonic()
        await self._bus.publish(self._session_id, {"type": "token", "content": chunk})


async def stream_next_event(
    sub: _Subscriber,
    *,
    timeout: float = 15.0,
    batch_ms: float = 50.0,
    batch_chars: int = 256,
) -> dict[str, Any]:
    """Wait for the next milestone or batched token event."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError

        try:
            return sub.milestones.get_nowait()
        except asyncio.QueueEmpty:
            pass

        async with sub._token_lock:
            if sub.token_buffer:
                elapsed_ms = (time.monotonic() - sub.token_updated_at) * 1000
                if elapsed_ms >= batch_ms or len(sub.token_buffer) >= batch_chars:
                    text = sub.token_buffer
                    sub.token_buffer = ""
                    sub.token_updated_at = time.monotonic()
                    return {"type": "token", "content": text}

        wait_for = min(remaining, max(batch_ms / 1000.0, 0.01))
        try:
            return await asyncio.wait_for(sub.milestones.get(), timeout=wait_for)
        except asyncio.TimeoutError:
            async with sub._token_lock:
                if sub.token_buffer:
                    text = sub.token_buffer
                    sub.token_buffer = ""
                    sub.token_updated_at = time.monotonic()
                    return {"type": "token", "content": text}
            if time.monotonic() >= deadline:
                raise asyncio.TimeoutError from None
