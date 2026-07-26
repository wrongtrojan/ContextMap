"""AutoRE RHF three-stage relation extraction."""

from __future__ import annotations

import re
import uuid

from services.kg.autore_runtime import AutoRERuntimeConfig, config_from_yaml, generate_text
from services.kg.prompts import facts_prompt, head_prompt, relation_prompt
from services.kg.types import TextChunk, Triple

_TRIPLE_RE = re.compile(
    r"\[\s*(?P<head>[^\],]+?)\s*,\s*(?P<rel>[^\],]+?)\s*,\s*(?P<tail>[^\],]+?)\s*\]",
    re.IGNORECASE,
)
_NO_OUTPUT = {"no relation", "no entity", "no fact", "none", "n/a"}


def _runtime_config() -> AutoRERuntimeConfig:
    return config_from_yaml()


def _parse_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.splitlines():
        item = line.strip().lstrip("-*•").strip()
        if not item or item.lower() in _NO_OUTPUT:
            continue
        lines.append(item)
    return lines


def _parse_triples(raw: str, *, default_relation: str, default_head: str) -> list[tuple[str, str, str]]:
    triples: list[tuple[str, str, str]] = []
    for match in _TRIPLE_RE.finditer(raw):
        triples.append((match.group("head").strip(), match.group("rel").strip(), match.group("tail").strip()))
    if triples:
        return triples
    for line in _parse_lines(raw):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 3:
            triples.append((parts[0], parts[1], parts[2]))
        elif default_relation and default_head and line and line.lower() not in _NO_OUTPUT:
            triples.append((default_head, default_relation, line))
    return triples


def extract_triples_from_chunk(
    chunk: TextChunk,
    *,
    allow_download: bool = True,
) -> list[Triple]:
    config = _runtime_config()
    passage = chunk.text
    triples: list[Triple] = []

    relation_raw = generate_text(
        config,
        "relation",
        relation_prompt(passage),
        allow_download=allow_download,
    )
    relations = _parse_lines(relation_raw)
    if not relations:
        return []

    for relation in relations:
        head_raw = generate_text(
            config,
            "head",
            head_prompt(relation, passage),
            allow_download=allow_download,
        )
        heads = _parse_lines(head_raw)
        if not heads:
            continue
        for head in heads:
            fact_raw = generate_text(
                config,
                "fact",
                facts_prompt(relation, head, passage),
                allow_download=allow_download,
            )
            for h, r, t in _parse_triples(fact_raw, default_relation=relation, default_head=head):
                if not h or not r or not t:
                    continue
                if h.lower() == t.lower():
                    continue
                triples.append(
                    Triple(
                        head=h,
                        relation=r,
                        tail=t,
                        confidence=1.0,
                        evidence_span=passage[:300],
                        source_unit_id=chunk.source_unit_id,
                        source_modality=chunk.modality,
                    )
                )
    return triples


def extract_triples_mock(chunk: TextChunk) -> list[Triple]:
    """Deterministic fallback for tests without GPU/models."""
    text = chunk.text
    if len(text) < 8:
        return []
    head = text.split("，")[0].split(",")[0][:40].strip()
    tail = text.split("。")[0][-40:].strip() if "。" in text else text[-40:].strip()
    if not head or not tail or head == tail:
        return []
    return [
        Triple(
            head=head,
            relation="相关",
            tail=tail,
            confidence=0.5,
            evidence_span=text[:200],
            source_unit_id=chunk.source_unit_id,
            source_modality=chunk.modality,
        )
    ]
