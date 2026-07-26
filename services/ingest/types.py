"""Shared ingest unit definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from database.enums import ContentType


@dataclass
class IngestUnit:
    content_type: ContentType
    search_text: str
    content_ref: str
    search_tokens: str | None = None
    timestamp_anchor: float = 0.0
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    local_blob_path: str | None = None
    embed: bool = True
