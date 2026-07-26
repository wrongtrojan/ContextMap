"""Threshold gates producing proceed/refetch recommendations."""

from __future__ import annotations

from typing import Any

from services.evaluate.types import RefetchHint


def should_run_audit(
    *,
    max_rerank: float,
    coverage: float,
    thresholds: dict[str, Any],
) -> bool:
    if not thresholds.get("audit_on_borderline", True):
        return False
    low = float(thresholds.get("borderline_low", 0.40))
    high = float(thresholds.get("borderline_high", 0.55))
    min_coverage = float(thresholds.get("min_coverage", 0.60))
    if low <= max_rerank < high:
        return True
    return coverage < min_coverage


def build_recommendation(
    *,
    max_rerank: float,
    coverage: float,
    thresholds: dict[str, Any],
    missing_facets: list[str],
    audit: dict[str, Any] | None = None,
) -> tuple[str, float, RefetchHint | None]:
    proceed_rerank = float(thresholds.get("proceed_rerank", 0.55))
    min_coverage = float(thresholds.get("min_coverage", 0.60))

    if audit and isinstance(audit.get("action"), str):
        recommendation = audit["action"] if audit["action"] in ("proceed", "refetch") else None
        if recommendation == "proceed":
            confidence = float(audit.get("confidence_score") or max_rerank)
            return "proceed", confidence, None
        if recommendation == "refetch":
            confidence = float(audit.get("confidence_score") or max_rerank)
            hint = _refetch_hint(missing_facets, audit)
            return "refetch", confidence, hint

    if max_rerank >= proceed_rerank and coverage >= min_coverage:
        confidence = min(1.0, (max_rerank + coverage) / 2)
        return "proceed", confidence, None

    confidence = max(0.0, min(1.0, max_rerank))
    return "refetch", confidence, _refetch_hint(missing_facets, audit)


def _refetch_hint(missing_facets: list[str], audit: dict[str, Any] | None) -> RefetchHint:
    append = list(missing_facets)
    if audit:
        suggested = audit.get("suggested_keywords") or audit.get("missing_info")
        if isinstance(suggested, list):
            append.extend(str(item) for item in suggested if str(item).strip())
        elif isinstance(suggested, str) and suggested.strip():
            append.append(suggested.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in append:
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(keyword)
    return RefetchHint(top_k_multiplier=1.5, append_keywords=deduped)
