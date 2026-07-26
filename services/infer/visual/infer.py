"""Batch visual inference."""

from __future__ import annotations

from services.infer.types import InferResult, VisualRequest
from services.infer.visual.expert import get_visual_expert


def run_visual_batch(requests: list[VisualRequest]) -> list[InferResult]:
    expert = get_visual_expert()
    if expert is None:
        return []

    results: list[InferResult] = []
    for req in requests:
        try:
            caption = expert.describe(
                query=req.query,
                image_path=req.image_path,
                evidence_text=str(req.evidence.get("content") or ""),
            )
        except Exception as exc:
            caption = f"[visual inference failed: {exc}]"
        results.append(
            InferResult(
                kind="visual",
                content=caption,
                content_unit_id=str(req.evidence.get("content_unit_id") or "") or None,
                image_path=req.image_path,
            )
        )
    return results
