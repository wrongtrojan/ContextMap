"""Chinese/English text segmentation for FTS indexing and query tokenization."""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_JIEBA = None


def _jieba():
    global _JIEBA
    if _JIEBA is None:
        import jieba

        _JIEBA = jieba
    return _JIEBA


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _is_noise_token(token: str) -> bool:
    stripped = token.strip()
    if not stripped:
        return True
    if has_cjk(stripped):
        return len(stripped) < 1
    return len(stripped) < 2


def segment_tokens(text: str) -> list[str]:
    """Return deduplicated search tokens preserving order."""
    text = (text or "").strip()
    if not text:
        return []

    if has_cjk(text):
        raw = _jieba().lcut(text, cut_all=False)
    else:
        raw = re.split(r"[^\w]+", text.lower())

    seen: set[str] = set()
    tokens: list[str] = []
    for token in raw:
        cleaned = token.strip()
        if _is_noise_token(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(cleaned)
    return tokens


def segment_for_fts(text: str) -> str:
    """Space-joined tokens suitable for PostgreSQL simple FTS config."""
    tokens = segment_tokens(text)
    if tokens:
        return " ".join(tokens)
    return (text or "").strip()


def expand_query_tokens(*parts: str) -> list[str]:
    """Flatten keywords and query text into unique search tokens."""
    seen: set[str] = set()
    tokens: list[str] = []
    for part in parts:
        for token in segment_tokens(part):
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
    return tokens
