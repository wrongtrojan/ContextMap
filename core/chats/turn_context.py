"""Per-turn execution context (isolated via contextvars for concurrent turns)."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnContext:
    session_id: uuid.UUID
    turn_seq: int
    assistant_message_id: uuid.UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_current_turn: ContextVar[TurnContext | None] = ContextVar("chat_turn_context", default=None)


def get_turn_context() -> TurnContext | None:
    return _current_turn.get()


def require_turn_context() -> TurnContext:
    ctx = _current_turn.get()
    if ctx is None:
        raise RuntimeError("No active turn context")
    return ctx


def set_turn_context(ctx: TurnContext | None) -> Any:
    return _current_turn.set(ctx)


def reset_turn_context(token: Any) -> None:
    _current_turn.reset(token)
