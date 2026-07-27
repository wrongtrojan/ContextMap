from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CleanupReport:
    scanned: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)
