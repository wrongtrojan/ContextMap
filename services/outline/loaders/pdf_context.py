"""Load condensed PDF context from MinerU middle.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TEXT_BLOCK_TYPES = {"text", "title", "list", "index", "ref_text", "abstract"}


@dataclass
class PdfContextStats:
    lines: int = 0
    pages: int = 0
    truncated: bool = False
    used_md_fallback: bool = False


@dataclass
class PdfContextResult:
    context: str
    stats: PdfContextStats = field(default_factory=PdfContextStats)
    max_page: int = 1


def _block_text(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            content = span.get("content")
            if content:
                parts.append(str(content))
    return " ".join(parts).strip()


def _table_caption(block: dict[str, Any]) -> str | None:
    for sub in block.get("blocks", []):
        if sub.get("type") == "table_caption":
            text = _block_text(sub)
            if text:
                return text
    return None


def _page_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    para_blocks = page.get("para_blocks") or []
    if para_blocks:
        return para_blocks
    return page.get("preproc_blocks") or []


def _lines_from_middle(middle_path: Path, *, include_table_captions: bool) -> tuple[list[str], int]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    lines: list[str] = []
    max_page = 1
    for page in middle.get("pdf_info", []):
        page_idx = int(page.get("page_idx", 0))
        page_number = page_idx + 1
        max_page = max(max_page, page_number)
        for block in _page_blocks(page):
            block_type = block.get("type")
            if block_type in _TEXT_BLOCK_TYPES:
                text = _block_text(block)
                if text:
                    lines.append(f"[p{page_number}] {text}")
            elif include_table_captions and block_type == "table":
                caption = _table_caption(block)
                if caption:
                    lines.append(f"[p{page_number}] [table] {caption}")
    return lines, max_page


def _md_fallback(md_path: Path, max_chars: int) -> str:
    text = md_path.read_text(encoding="utf-8").strip()
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def load_pdf_context(
    middle_path: Path,
    md_path: Path | None,
    *,
    max_chars: int,
    min_middle_lines: int = 5,
    include_table_captions: bool = True,
) -> PdfContextResult:
    lines, max_page = _lines_from_middle(middle_path, include_table_captions=include_table_captions)
    stats = PdfContextStats(lines=len(lines), pages=max_page)

    if len(lines) < min_middle_lines and md_path and md_path.exists():
        context = _md_fallback(md_path, max_chars)
        stats.used_md_fallback = True
        stats.lines = context.count("\n") + 1 if context else 0
        return PdfContextResult(context=context, stats=stats, max_page=max_page)

    context = "\n".join(lines)
    if len(context) > max_chars:
        context = context[:max_chars]
        stats.truncated = True
    stats.lines = len(lines)
    return PdfContextResult(context=context, stats=stats, max_page=max_page)
