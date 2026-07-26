"""Build TextChunks from content_units for KG extraction."""

from __future__ import annotations

import re
import uuid

from database.enums import ContentType
from database.repositories import ContentUnitRepo
from database.schemas import ContentUnitRead
from database.session import get_session
from services.kg.config import load_kg_config
from services.kg.types import TextChunk

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？.!?])\s*")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def _split_text(text: str, max_tokens: int) -> list[str]:
    if _estimate_tokens(text) <= max_tokens:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        tokens = _estimate_tokens(sentence)
        if current and current_tokens + tokens > max_tokens:
            parts.append(" ".join(current))
            current = [sentence]
            current_tokens = tokens
        else:
            current.append(sentence)
            current_tokens += tokens
    if current:
        parts.append(" ".join(current))
    return parts or [text]


def _content_types_from_config() -> set[ContentType]:
    cfg = load_kg_config()
    raw = cfg.get("extract", {}).get("content_types") or ["text", "transcript"]
    mapping = {
        "text": ContentType.TEXT,
        "transcript": ContentType.TRANSCRIPT,
    }
    return {mapping[item] for item in raw if item in mapping}


def units_to_chunks(
    units: list[ContentUnitRead],
    *,
    asset_id: uuid.UUID,
    modality: str,
    max_tokens: int | None = None,
) -> list[TextChunk]:
    cfg = load_kg_config()
    limit = max_tokens or int(cfg.get("chunk_max_tokens", 512))
    allowed = _content_types_from_config()
    chunks: list[TextChunk] = []

    transcript_units = [u for u in units if u.content_type in allowed]
    transcript_units.sort(key=lambda u: (u.chunk_index, u.content_type.value))

    i = 0
    while i < len(transcript_units):
        unit = transcript_units[i]
        text = unit.search_text.strip()
        if not text:
            i += 1
            continue

        if unit.content_type == ContentType.TRANSCRIPT and _estimate_tokens(text) < 64:
            merged = text
            j = i + 1
            while j < len(transcript_units) and _estimate_tokens(merged) < limit // 2:
                nxt = transcript_units[j]
                if nxt.content_type != ContentType.TRANSCRIPT:
                    break
                merged = f"{merged} {nxt.search_text.strip()}".strip()
                j += 1
            if j > i + 1:
                chunks.append(
                    TextChunk(
                        text=merged,
                        source_unit_id=unit.id,
                        asset_id=asset_id,
                        modality=modality,
                        timestamp=unit.timestamp_anchor,
                        chunk_index=unit.chunk_index,
                    )
                )
                i = j
                continue

        for part in _split_text(text, limit):
            chunks.append(
                TextChunk(
                    text=part,
                    source_unit_id=unit.id,
                    asset_id=asset_id,
                    modality=modality,
                    timestamp=unit.timestamp_anchor,
                    chunk_index=unit.chunk_index,
                )
            )
        i += 1

    return chunks


async def collect_chunks(asset_id: uuid.UUID, modality: str) -> list[TextChunk]:
    async with get_session() as session:
        units = await ContentUnitRepo(session).list_by_asset(asset_id)
    return units_to_chunks(units, asset_id=asset_id, modality=modality)
