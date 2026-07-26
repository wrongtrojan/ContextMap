"""Route infer tools from query, evidence, and evaluation hints."""

from __future__ import annotations

from typing import Any

from services.evaluate.types import EvaluationReport, InferHints
from services.infer.config import load_infer_config
from services.infer.types import InferTrigger, SandboxRequest, VisualRequest
from services.infer.visual.resolve_media import resolve_image_path


def route_infer(
    *,
    query: str,
    evidence: list[dict],
    eval_report: EvaluationReport | None = None,
    config: dict[str, Any] | None = None,
) -> InferTrigger:
    cfg = config or load_infer_config()
    route_cfg = cfg.get("route") or {}
    sandbox_cfg = cfg.get("sandbox") or {}
    visual_cfg = cfg.get("visual") or {}

    hints: InferHints = eval_report.infer_hints if eval_report else InferHints()
    sandbox_keywords = [str(k).lower() for k in (route_cfg.get("sandbox_keywords") or [])]
    visual_types = {str(t).lower() for t in (route_cfg.get("visual_content_types") or [])}
    visual_min = float(route_cfg.get("visual_min_rerank", 0.45))

    run_sandbox = bool(sandbox_cfg.get("enabled", True)) and hints.need_sandbox
    if not run_sandbox:
        q_lower = query.lower()
        run_sandbox = any(token in q_lower for token in sandbox_keywords)

    visual_candidates = list(hints.visual_candidates)
    if not visual_candidates:
        for item in evidence:
            metadata = item.get("metadata") or {}
            content_type = str(metadata.get("type") or "").lower()
            rerank_score = float(item.get("rerank_score") or 0.0)
            if content_type in visual_types and (
                metadata.get("has_visual_asset") or rerank_score >= visual_min
            ):
                visual_candidates.append(item)
            for linked in item.get("linked_media") or []:
                visual_candidates.append(linked)

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in visual_candidates:
        unit_id = str(item.get("content_unit_id") or "")
        if unit_id in seen:
            continue
        seen.add(unit_id)
        deduped.append(item)

    visual_requests: list[VisualRequest] = []
    if visual_cfg.get("enabled", True):
        max_images = int(visual_cfg.get("max_images", 4))
        for item in deduped[:max_images]:
            path = resolve_image_path(item)
            if path is None:
                continue
            visual_requests.append(
                VisualRequest(query=query, evidence=item, image_path=str(path))
            )

    sandbox_request = SandboxRequest(expression="", mode="eval") if run_sandbox else None

    return InferTrigger(
        run_sandbox=run_sandbox and sandbox_request is not None,
        run_visual=bool(visual_requests),
        sandbox_request=sandbox_request,
        visual_requests=visual_requests,
    )
