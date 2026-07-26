"""KG extraction data types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextChunk:
    text: str
    source_unit_id: uuid.UUID
    asset_id: uuid.UUID
    modality: str
    timestamp: float = 0.0
    chunk_index: int = 0


@dataclass
class Triple:
    head: str
    relation: str
    tail: str
    confidence: float = 1.0
    evidence_span: str = ""
    source_unit_id: uuid.UUID | None = None
    source_modality: str = ""


@dataclass
class ExtractionResult:
    asset_id: uuid.UUID
    chunks: list[TextChunk] = field(default_factory=list)
    triples: list[Triple] = field(default_factory=list)
    action: str = "extracted"
    metadata: dict[str, Any] = field(default_factory=dict)
