"""Facet coverage scoring for retrieved evidence."""

from __future__ import annotations

from services.common.text_segment import expand_query_tokens


def extract_facets(*, search_needs: dict, user_query: str = "") -> list[str]:
    params = search_needs.get("search_params") or {}
    keywords = [str(k).strip() for k in (params.get("keywords") or []) if str(k).strip()]
    semantic = str(params.get("semantic_query") or "").strip()
    facets = expand_query_tokens(user_query, semantic, *keywords)
    return facets


def facet_hits_in_text(facets: list[str], text: str) -> list[str]:
    lowered = (text or "").lower()
    hits: list[str] = []
    for facet in facets:
        if facet.lower() in lowered:
            hits.append(facet)
    return hits


def compute_coverage(
    *,
    facets: list[str],
    evidence: list[dict],
    top_k: int | None = None,
) -> tuple[float, list[str]]:
    if not facets:
        return 1.0, []

    pool = evidence[:top_k] if top_k else evidence
    covered: set[str] = set()
    for item in pool:
        content = str(item.get("content") or "")
        for facet in facet_hits_in_text(facets, content):
            covered.add(facet.lower())

    missing = [facet for facet in facets if facet.lower() not in covered]
    coverage = len(covered) / len(facets)
    return coverage, missing


def score_evidence_facets(*, facets: list[str], evidence: dict) -> list[str]:
    return facet_hits_in_text(facets, str(evidence.get("content") or ""))
