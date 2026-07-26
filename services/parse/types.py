"""Parse result summary types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseSummary:
    source_path: str
    modality: str
    action: str
    skip_reason: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    middle_path: str | None = None
    md_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "modality": self.modality,
            "action": self.action,
            "skip_reason": self.skip_reason,
            "coverage": self.coverage,
            "error": self.error,
            "middle_path": self.middle_path,
            "md_path": self.md_path,
        }
