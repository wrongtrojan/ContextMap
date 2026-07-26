"""Infer module types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SandboxRequest:
    expression: str
    mode: str = "eval"
    symbol: str = "x"

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "mode": self.mode,
            "symbol": self.symbol,
        }


@dataclass
class SandboxResult:
    status: Literal["success", "error"]
    result: Any = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result": self.result,
            "message": self.message,
        }


@dataclass
class VisualRequest:
    query: str
    evidence: dict[str, Any]
    image_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "evidence": self.evidence,
            "image_path": self.image_path,
        }


@dataclass
class InferResult:
    kind: Literal["sandbox", "visual"]
    content: str
    source_expression: str | None = None
    content_unit_id: str | None = None
    image_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content": self.content,
            "source_expression": self.source_expression,
            "content_unit_id": self.content_unit_id,
            "image_path": self.image_path,
        }


@dataclass
class InferTrigger:
    run_sandbox: bool = False
    run_visual: bool = False
    sandbox_request: SandboxRequest | None = None
    visual_requests: list[VisualRequest] = field(default_factory=list)
