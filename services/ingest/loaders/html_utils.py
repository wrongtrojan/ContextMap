"""Convert MinerU table HTML into plain text for embedding."""

from __future__ import annotations

import html
import re

_EQ_PATTERN = re.compile(r"<eq>(.*?)</eq>", re.DOTALL | re.IGNORECASE)
_ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_PATTERN = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_tags(value: str) -> str:
    text = _EQ_PATTERN.sub(r"\1", value)
    text = _TAG_PATTERN.sub("", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def html_table_to_text(table_html: str) -> str:
    """Flatten a MinerU table HTML snippet to pipe-separated rows."""
    if not table_html or not table_html.strip():
        return ""

    rows: list[str] = []
    for row_match in _ROW_PATTERN.finditer(table_html):
        cells = [_strip_tags(cell) for cell in _CELL_PATTERN.findall(row_match.group(1))]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))

    if rows:
        return "\n".join(rows)

    return _strip_tags(table_html)
