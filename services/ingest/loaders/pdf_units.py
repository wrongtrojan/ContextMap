"""Load content units from PDF MinerU middle.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from database.enums import ContentType
from services.ingest.loaders.html_utils import html_table_to_text
from services.ingest.types import IngestUnit

_TEXT_BLOCK_TYPES = {"text", "title", "list", "index", "ref_text", "abstract"}
_HEADING_BLOCK_TYPES = {"title"}


@dataclass
class PdfLoadStats:
    block_types_seen: dict[str, int] = field(default_factory=dict)
    units_by_type: dict[str, int] = field(default_factory=dict)
    disk_images: int = 0
    referenced_images: set[str] = field(default_factory=set)
    uploaded_image_candidates: set[str] = field(default_factory=set)

    def bump_block(self, block_type: str | None) -> None:
        if not block_type:
            return
        self.block_types_seen[block_type] = self.block_types_seen.get(block_type, 0) + 1

    def bump_unit(self, content_type: ContentType) -> None:
        key = content_type.value
        self.units_by_type[key] = self.units_by_type.get(key, 0) + 1


def _normalize_bbox(raw: Any) -> list[float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None


def _block_text(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            content = span.get("content")
            if content:
                parts.append(str(content))
    return " ".join(parts).strip()


def _page_headings(blocks: list[dict[str, Any]]) -> list[str]:
    headings: list[str] = []
    for block in blocks:
        if block.get("type") in _HEADING_BLOCK_TYPES:
            text = _block_text(block)
            if text:
                headings.append(text)
    return headings


def _nearest_heading(headings: list[str]) -> str | None:
    return headings[-1] if headings else None


def _extract_image_info(block: dict[str, Any]) -> tuple[str | None, str | None]:
    image_path: str | None = None
    caption: str | None = None
    for sub in block.get("blocks", []):
        sub_type = sub.get("type")
        if sub_type in {"image_body", "chart_body"}:
            for line in sub.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("image_path"):
                        image_path = span["image_path"]
        elif sub_type in {"image_caption", "chart_caption"}:
            text = _block_text(sub)
            if text:
                caption = text
    return image_path, caption


def _extract_table_info(block: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    html_content: str | None = None
    image_path: str | None = None
    caption: str | None = None
    for sub in block.get("blocks", []):
        sub_type = sub.get("type")
        if sub_type == "table_body":
            for line in sub.get("lines", []):
                for span in line.get("spans", []):
                    html_content = html_content or span.get("html")
                    if span.get("image_path"):
                        image_path = span["image_path"]
        elif sub_type == "table_caption":
            text = _block_text(sub)
            if text:
                caption = text
    return html_content, image_path, caption


def _page_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    para_blocks = page.get("para_blocks") or []
    if para_blocks:
        return para_blocks
    return page.get("preproc_blocks") or []


def _build_image_unit(
    *,
    image_filename: str,
    caption: str | None,
    headings: list[str],
    page_number: int,
    chunk_index: int,
    images_dir: Path,
    stats: PdfLoadStats,
    block_type: str,
    bbox: list[float] | None = None,
) -> IngestUnit | None:
    if not image_filename:
        return None

    local_path = images_dir / image_filename
    stats.referenced_images.add(image_filename)
    if local_path.exists():
        stats.uploaded_image_candidates.add(image_filename)

    if caption:
        search_text = caption
        context_source = "caption"
        context_confidence = 1.0
        embed = True
    else:
        heading = _nearest_heading(headings)
        if heading:
            search_text = f"{heading} (page {page_number})"
            context_source = "section_heading"
            context_confidence = 0.6
            embed = True
        else:
            search_text = f"[Figure page {page_number}]"
            context_source = "page_only"
            context_confidence = 0.1
            embed = False

    metadata: dict[str, Any] = {
        "page_label": page_number,
        "image_filename": image_filename,
        "context_source": context_source,
        "context_confidence": context_confidence,
        "caption_text": caption,
        "source_block_type": block_type,
    }
    if bbox is not None:
        metadata["bbox"] = bbox

    unit = IngestUnit(
        content_type=ContentType.IMAGE,
        search_text=search_text,
        content_ref=image_filename,
        timestamp_anchor=float(page_number),
        chunk_index=chunk_index,
        metadata=metadata,
        local_blob_path=str(local_path) if local_path.exists() else None,
        embed=embed,
    )
    stats.bump_unit(ContentType.IMAGE)
    return unit


def load_pdf_units(middle_path: Path, images_dir: Path) -> tuple[list[IngestUnit], PdfLoadStats]:
    with middle_path.open(encoding="utf-8") as handle:
        middle = json.load(handle)

    units: list[IngestUnit] = []
    chunk_index = 0
    stats = PdfLoadStats()
    stats.disk_images = len(list(images_dir.glob("*"))) if images_dir.exists() else 0

    for page in middle.get("pdf_info", []):
        page_idx = int(page.get("page_idx", 0))
        page_number = page_idx + 1
        page_size = page.get("page_size")
        blocks = _page_blocks(page)
        headings = _page_headings(blocks)

        for block in blocks:
            block_type = block.get("type")
            stats.bump_block(block_type)
            bbox = _normalize_bbox(block.get("bbox"))

            if block_type in _TEXT_BLOCK_TYPES:
                text = _block_text(block)
                if not text:
                    continue
                metadata: dict[str, Any] = {
                    "page_label": page_number,
                    "block_type": block_type,
                }
                if bbox is not None:
                    metadata["bbox"] = bbox
                if isinstance(page_size, (list, tuple)) and len(page_size) >= 2:
                    metadata["page_size"] = [float(page_size[0]), float(page_size[1])]
                units.append(
                    IngestUnit(
                        content_type=ContentType.TEXT,
                        search_text=text,
                        content_ref=text[:2000],
                        timestamp_anchor=float(page_number),
                        chunk_index=chunk_index,
                        metadata=metadata,
                    )
                )
                stats.bump_unit(ContentType.TEXT)
                chunk_index += 1
            elif block_type in {"image", "chart"}:
                image_filename, caption = _extract_image_info(block)
                unit = _build_image_unit(
                    image_filename=image_filename or "",
                    caption=caption,
                    headings=headings,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    images_dir=images_dir,
                    stats=stats,
                    block_type=block_type,
                    bbox=bbox,
                )
                if unit is None:
                    continue
                if isinstance(page_size, (list, tuple)) and len(page_size) >= 2:
                    unit.metadata["page_size"] = [float(page_size[0]), float(page_size[1])]
                units.append(unit)
                chunk_index += 1
            elif block_type == "table":
                html_content, image_filename, caption = _extract_table_info(block)
                plain_table = html_table_to_text(html_content or "")

                if caption and plain_table:
                    search_text = f"{caption}\n{plain_table}"
                    context_source = "caption"
                    embed = True
                elif plain_table:
                    search_text = plain_table
                    context_source = "html_only"
                    embed = True
                elif caption:
                    search_text = caption
                    context_source = "caption"
                    embed = True
                else:
                    search_text = f"[Table page {page_number}]"
                    context_source = "page_only"
                    embed = False

                local_path = None
                if image_filename:
                    stats.referenced_images.add(image_filename)
                    candidate = images_dir / image_filename
                    if candidate.exists():
                        local_path = str(candidate)
                        stats.uploaded_image_candidates.add(image_filename)

                table_meta: dict[str, Any] = {
                    "page_label": page_number,
                    "block_type": "table",
                    "caption_text": caption,
                    "context_source": context_source,
                    "image_filename": image_filename,
                }
                if bbox is not None:
                    table_meta["bbox"] = bbox
                if isinstance(page_size, (list, tuple)) and len(page_size) >= 2:
                    table_meta["page_size"] = [float(page_size[0]), float(page_size[1])]

                units.append(
                    IngestUnit(
                        content_type=ContentType.TABLE,
                        search_text=search_text,
                        content_ref=(plain_table or search_text)[:4000],
                        timestamp_anchor=float(page_number),
                        chunk_index=chunk_index,
                        metadata=table_meta,
                        local_blob_path=local_path,
                        embed=embed,
                    )
                )
                stats.bump_unit(ContentType.TABLE)
                chunk_index += 1

    return units, stats
