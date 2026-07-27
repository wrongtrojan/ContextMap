"""Batch visual inference."""

from __future__ import annotations

from typing import Any

from services.infer.config import load_infer_config
from services.infer.preflight import check_visual_runtime
from services.infer.types import InferResult, VisualRequest
from services.infer.visual.expert import get_visual_expert


def _unavailable_results(
    requests: list[VisualRequest],
    message: str,
) -> list[InferResult]:
    return [
        InferResult(
            kind="visual",
            content=f"[visual unavailable: {message}]",
            content_unit_id=str(req.evidence.get("content_unit_id") or "") or None,
            image_path=req.image_path,
        )
        for req in requests
    ]


def run_visual_batch(
    requests: list[VisualRequest],
    *,
    config: dict[str, Any] | None = None,
    fail_open: bool = True,
) -> list[InferResult]:
    if not requests:
        return []

    cfg = config or load_infer_config()
    preflight_error = check_visual_runtime(cfg)
    if preflight_error is not None:
        if fail_open:
            return _unavailable_results(requests, preflight_error)
        raise RuntimeError(preflight_error)

    expert = get_visual_expert()
    if expert is None:
        if fail_open:
            return _unavailable_results(requests, "visual inference disabled")
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
            if fail_open:
                caption = f"[visual inference failed: {exc}]"
            else:
                raise
        results.append(
            InferResult(
                kind="visual",
                content=caption,
                content_unit_id=str(req.evidence.get("content_unit_id") or "") or None,
                image_path=req.image_path,
            )
        )
    return results
