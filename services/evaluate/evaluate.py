"""Evaluate evidence relevance (pure function, no retrieval side effects)."""

from __future__ import annotations

from typing import Any

from services.evaluate.audit import run_audit
from services.evaluate.config import load_evaluate_config
from services.evaluate.coverage import compute_coverage, extract_facets, score_evidence_facets
from services.evaluate.gates import build_recommendation, should_run_audit
from services.evaluate.rerank import ScoreFn, rerank_evidence
from services.evaluate.types import EvaluationReport, EvidenceScore, InferHints


def _semantic_query(search_needs: dict, user_query: str) -> str:
    params = search_needs.get("search_params") or {}
    semantic = str(params.get("semantic_query") or "").strip()
    if semantic:
        return semantic
    keywords = params.get("keywords") or []
    joined = " ".join(str(k) for k in keywords if str(k).strip())
    return joined or user_query


def _infer_hints(
    *,
    query: str,
    evidence: list[dict],
    scores: list[EvidenceScore],
    audit: dict[str, Any] | None,
    route_cfg: dict[str, Any] | None = None,
) -> InferHints:
    route_cfg = route_cfg or {}
    sandbox_keywords = [str(k).lower() for k in (route_cfg.get("sandbox_keywords") or [])]
    visual_types = {str(t).lower() for t in (route_cfg.get("visual_content_types") or ["frame", "image", "table"])}
    visual_min = float(route_cfg.get("visual_min_rerank", 0.45))
    visual_query_tokens = ["图", "图表", "帧", "示意图", "figure", "diagram", "image", "chart"]

    score_by_id = {score.content_unit_id: score.rerank_score for score in scores}
    need_sandbox = bool(audit and audit.get("need_sandbox"))
    if not need_sandbox:
        q_lower = query.lower()
        need_sandbox = any(token in q_lower for token in sandbox_keywords)
        if not need_sandbox:
            for item in evidence:
                content = str(item.get("content") or "").lower()
                if any(token in content for token in ("\\frac", "\\sum", "equation", "方程", "求解")):
                    need_sandbox = any(token in q_lower for token in sandbox_keywords)
                    break

    visual_candidates: list[dict] = []
    q_visual = any(token in query for token in visual_query_tokens)
    for item in evidence:
        metadata = item.get("metadata") or {}
        content_type = str(metadata.get("type") or "").lower()
        unit_id = str(item.get("content_unit_id") or "")
        rerank_score = score_by_id.get(unit_id, 0.0)
        has_visual = bool(metadata.get("has_visual_asset"))
        if content_type in visual_types and (has_visual or rerank_score >= visual_min or q_visual):
            enriched = dict(item)
            enriched["rerank_score"] = rerank_score
            visual_candidates.append(enriched)

    if audit and audit.get("need_visual"):
        for item in evidence:
            metadata = item.get("metadata") or {}
            if metadata.get("has_visual_asset") and item not in visual_candidates:
                visual_candidates.append(dict(item))

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in visual_candidates:
        unit_id = str(item.get("content_unit_id") or "")
        if unit_id in seen:
            continue
        seen.add(unit_id)
        deduped.append(item)

    return InferHints(need_sandbox=need_sandbox, visual_candidates=deduped)


async def evaluate_evidence(
    *,
    user_query: str,
    search_needs: dict[str, Any],
    evidence: list[dict],
    retry_index: int = 0,
    config: dict[str, Any] | None = None,
    route_cfg: dict[str, Any] | None = None,
    score_fn: ScoreFn | None = None,
    run_llm_audit: bool | None = None,
) -> EvaluationReport:
    cfg = config or load_evaluate_config()
    thresholds = cfg.get("thresholds") or {}
    keep_top_k = int(cfg.get("keep_top_k", 8))
    min_keep = float(thresholds.get("min_keep_score", 0.35))

    query = _semantic_query(search_needs, user_query)
    facets = extract_facets(search_needs=search_needs, user_query=user_query)

    ranked = await rerank_evidence(query=query, evidence=list(evidence), score_fn=score_fn)
    coverage, missing_facets = compute_coverage(facets=facets, evidence=[item for item, _ in ranked])

    scores: list[EvidenceScore] = []
    filtered: list[dict] = []
    for item, rerank_score in ranked:
        if rerank_score < min_keep:
            continue
        unit_id = str(item.get("content_unit_id") or "")
        facet_hits = score_evidence_facets(facets=facets, evidence=item)
        reason = "rerank_pass" if rerank_score >= float(thresholds.get("proceed_rerank", 0.55)) else "rerank_low"
        scores.append(
            EvidenceScore(
                content_unit_id=unit_id,
                rerank_score=rerank_score,
                retrieval_score=item.get("score"),
                coverage_facets=facet_hits,
                decision_reason=reason,
            )
        )
        enriched = dict(item)
        enriched["rerank_score"] = rerank_score
        filtered.append(enriched)

    filtered = filtered[:keep_top_k]
    scores = scores[:keep_top_k]
    max_rerank = max((score.rerank_score for score in scores), default=0.0)

    audit = None
    do_audit = should_run_audit(max_rerank=max_rerank, coverage=coverage, thresholds=thresholds)
    if run_llm_audit is None:
        run_llm_audit = do_audit
    if run_llm_audit and do_audit:
        audit = await run_audit(query=user_query, evidence=filtered, retry_index=retry_index)

    recommendation, confidence, refetch_hint = build_recommendation(
        max_rerank=max_rerank,
        coverage=coverage,
        thresholds=thresholds,
        missing_facets=missing_facets,
        audit=audit,
    )

    infer_hints = _infer_hints(
        query=user_query,
        evidence=filtered,
        scores=scores,
        audit=audit,
        route_cfg=route_cfg,
    )

    return EvaluationReport(
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,
        evidence=filtered,
        scores=scores,
        missing_facets=missing_facets,
        refetch_hint=refetch_hint if recommendation == "refetch" else None,
        audit=audit,
        infer_hints=infer_hints,
    )
