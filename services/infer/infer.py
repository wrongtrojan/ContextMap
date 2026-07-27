"""Infer orchestration: sandbox + visual enrichment."""

from __future__ import annotations

from typing import Any

from services.evaluate.types import EvaluationReport
from services.infer.config import load_infer_config
from services.infer.preflight import check_sandbox_runtime, check_visual_runtime
from services.infer.route import route_infer
from services.infer.sandbox.prep import prepare_sandbox_request
from services.infer.sandbox.runner import run_sandbox
from services.infer.types import InferResult
from services.infer.visual.infer import run_visual_batch


async def run_infer(
    *,
    query: str,
    evidence: list[dict],
    eval_report: EvaluationReport | None = None,
    config: dict[str, Any] | None = None,
) -> list[InferResult]:
    cfg = config or load_infer_config()
    fail_open = bool(cfg.get("fail_open", True))
    trigger = route_infer(query=query, evidence=evidence, eval_report=eval_report, config=cfg)
    results: list[InferResult] = []

    if trigger.run_sandbox:
        sandbox_error = check_sandbox_runtime(cfg)
        if sandbox_error is not None:
            if fail_open:
                results.append(
                    InferResult(
                        kind="sandbox",
                        content=f"[sandbox unavailable: {sandbox_error}]",
                    )
                )
            else:
                raise RuntimeError(sandbox_error)
        else:
            sandbox_req = await prepare_sandbox_request(query=query, evidence=evidence)
            sandbox_result = await run_sandbox(sandbox_req, config=cfg)
            if sandbox_result.status == "success":
                results.append(
                    InferResult(
                        kind="sandbox",
                        content=str(sandbox_result.result),
                        source_expression=sandbox_req.expression,
                    )
                )
            else:
                message = str(sandbox_result.message or "sandbox failed")
                if fail_open:
                    results.append(
                        InferResult(
                            kind="sandbox",
                            content=f"[sandbox failed: {message}]",
                            source_expression=sandbox_req.expression,
                        )
                    )
                else:
                    raise RuntimeError(message)

    if trigger.run_visual and trigger.visual_requests:
        visual_error = check_visual_runtime(cfg)
        if visual_error is not None and not fail_open:
            raise RuntimeError(visual_error)
        results.extend(
            run_visual_batch(
                trigger.visual_requests,
                config=cfg,
                fail_open=fail_open,
            )
        )

    return results
