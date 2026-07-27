"""
Top-level chat turn LangGraph orchestration.

Nodes call domain services only; persistence and SSE live in ChatsManager.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from core.chats.config import load_chat_config
from core.chats.prompts import render_prompt
from database.session import get_session
from services.evaluate import evaluate_evidence
from services.evaluate.types import EvaluationReport, RefetchHint
from services.infer.infer import run_infer
from services.retrieval.expand_media import expand_linked_media
from services.retrieval.prepare import refine_query
from services.retrieval.search import hybrid_search

if TYPE_CHECKING:
    from core.chats_manager import ChatsManager


class ChatTurnState(TypedDict, total=False):
    session_id: str
    turn_seq: int
    user_query: str
    conversation_context: str
    search_needs: dict[str, Any]
    retry_index: int
    evaluation_history: list[dict[str, Any]]
    last_evaluation: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    infer_results: list[dict[str, Any]]
    answer: str | None
    error: str | None
    assistant_message_id: str | None
    _evaluation_report: EvaluationReport


def should_refetch(
    report: EvaluationReport | dict[str, Any] | None,
    *,
    retry_index: int,
    max_retries: int,
    stop_loss_confidence: float = 0.6,
) -> Literal["refetch", "proceed"]:
    if report is None:
        return "proceed"
    recommendation = report.recommendation if isinstance(report, EvaluationReport) else report.get("recommendation")
    confidence = report.confidence if isinstance(report, EvaluationReport) else float(report.get("confidence") or 0.0)
    if retry_index > 0 and confidence >= stop_loss_confidence:
        return "proceed"
    if recommendation == "proceed":
        return "proceed"
    if retry_index >= max_retries:
        return "proceed"
    return "refetch"


def apply_refetch_hint(search_needs: dict[str, Any], hint: RefetchHint | dict[str, Any] | None) -> dict[str, Any]:
    if hint is None:
        return search_needs
    adjusted = copy.deepcopy(search_needs)
    if isinstance(hint, RefetchHint):
        multiplier = hint.top_k_multiplier
        append_keywords = hint.append_keywords
        relax_modality = hint.relax_modality
    else:
        multiplier = float(hint.get("top_k_multiplier", 1.5))
        append_keywords = list(hint.get("append_keywords") or [])
        relax_modality = bool(hint.get("relax_modality"))

    params = adjusted.setdefault("search_params", {})
    current_top_k = int(params.get("top_k") or 8)
    params["top_k"] = max(1, int(current_top_k * multiplier))
    keywords = list(params.get("keywords") or [])
    keywords.extend(append_keywords)
    params["keywords"] = keywords

    if relax_modality:
        prefs = adjusted.setdefault("preferences", {})
        prefs["modality"] = None

    return adjusted


def merge_evidence(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {str(item.get("content_unit_id")) for item in existing if item.get("content_unit_id")}
    for item in new_items:
        unit_id = str(item.get("content_unit_id") or "")
        if unit_id and unit_id in seen:
            continue
        if unit_id:
            seen.add(unit_id)
        merged.append(item)
    merged.sort(key=lambda row: float(row.get("rerank_score") or row.get("score") or 0.0), reverse=True)
    return merged


def build_synthesize_prompt(state: ChatTurnState) -> str:
    evidence = state.get("evidence") or []
    infer_results = state.get("infer_results") or []
    last_eval = state.get("last_evaluation") or {}

    vlm_parts = [str(item.get("content") or "") for item in infer_results if item.get("kind") == "visual"]
    sandbox_parts = [str(item.get("content") or "") for item in infer_results if item.get("kind") == "sandbox"]

    return render_prompt(
        "synthesizer.jinja2",
        query=state.get("user_query") or "",
        docs=json.dumps(evidence[:12], ensure_ascii=False, indent=2),
        vlm_feedback="\n".join(vlm_parts) if vlm_parts else None,
        math_res="\n".join(sandbox_parts) if sandbox_parts else None,
        eval_report=json.dumps(last_eval, ensure_ascii=False, indent=2) if last_eval else None,
    )


def _report_from_state(state: ChatTurnState) -> EvaluationReport:
    report_obj = state.get("_evaluation_report")
    if isinstance(report_obj, EvaluationReport):
        return report_obj
    last = state.get("last_evaluation") or {}
    return EvaluationReport(
        recommendation=last.get("recommendation") or "proceed",
        confidence=float(last.get("confidence") or 0.0),
        evidence=list(state.get("evidence") or []),
        scores=[],
        refetch_hint=None,
    )


async def node_prepare(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("prepare")
    context = state.get("conversation_context") or state.get("user_query") or ""
    search_needs = await refine_query(context)
    return {"search_needs": search_needs, "retry_index": 0, "evaluation_history": [], "evidence": []}


async def node_research_search(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("research_search")
    search_needs = state.get("search_needs") or {}
    async with get_session() as db:
        result = await hybrid_search(db, search_needs=search_needs)
    if result.get("status") == "error":
        return {"error": result.get("message"), "evidence": []}
    evidence = result.get("results") or []
    await manager.emit_research_debug(result.get("debug") or {})
    return {"evidence": evidence}


async def node_research_evaluate(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("research_evaluate")
    cfg = load_chat_config()
    report = await evaluate_evidence(
        user_query=state.get("user_query") or "",
        search_needs=state.get("search_needs") or {},
        evidence=state.get("evidence") or [],
        retry_index=int(state.get("retry_index") or 0),
    )
    history = list(state.get("evaluation_history") or [])
    history.append(report.to_dict())

    chat_cfg = cfg.get("research") or {}
    merged_evidence = list(state.get("evidence") or [])
    if chat_cfg.get("merge_evidence_on_refetch", True):
        merged_evidence = merge_evidence(merged_evidence, report.evidence)
    else:
        merged_evidence = report.evidence

    await manager.emit_evaluation(report)
    return {
        "last_evaluation": report.to_dict(),
        "evaluation_history": history,
        "evidence": merged_evidence,
        "_evaluation_report": report,
    }


def route_after_evaluate(state: ChatTurnState) -> str:
    cfg = load_chat_config()
    research_cfg = cfg.get("research") or {}
    max_retries = int(research_cfg.get("max_retries", 2))
    stop_loss = float(research_cfg.get("stop_loss_confidence", 0.6))
    report = _report_from_state(state)
    decision = should_refetch(
        report,
        retry_index=int(state.get("retry_index") or 0),
        max_retries=max_retries,
        stop_loss_confidence=stop_loss,
    )
    return "apply_refetch" if decision == "refetch" else "expand_media"


async def node_apply_refetch(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("apply_refetch")
    last = state.get("last_evaluation") or {}
    hint = last.get("refetch_hint")
    search_needs = apply_refetch_hint(state.get("search_needs") or {}, hint)
    await manager.emit_refetch(hint)
    return {
        "search_needs": search_needs,
        "retry_index": int(state.get("retry_index") or 0) + 1,
    }


async def node_expand_media(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("expand_media")
    cfg = load_chat_config()
    window_sec = float((cfg.get("expand_media") or {}).get("window_sec", 2.0))
    async with get_session() as db:
        evidence = await expand_linked_media(db, state.get("evidence") or [], window_sec=window_sec)
    assistant_id = await manager.ensure_assistant_placeholder()
    await manager.persist_evidence(evidence, assistant_message_id=assistant_id)
    return {"evidence": evidence, "assistant_message_id": assistant_id}


async def node_infer(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("infer")
    report_obj = state.get("_evaluation_report")
    if not isinstance(report_obj, EvaluationReport):
        report_obj = None
    results = await run_infer(
        query=state.get("user_query") or "",
        evidence=state.get("evidence") or [],
        eval_report=report_obj,
    )
    payload = [item.to_dict() for item in results]
    await manager.emit_infer_results(payload)
    return {"infer_results": payload}


async def node_synthesize(state: ChatTurnState, manager: ChatsManager) -> dict[str, Any]:
    await manager.on_step_start("synthesize")
    if state.get("error"):
        return {}
    answer = await manager.stream_synthesize(state)
    return {"answer": answer}


def build_chat_graph(manager: ChatsManager):
    graph = StateGraph(ChatTurnState)

    async def prepare(state: ChatTurnState):
        return await node_prepare(state, manager)

    async def research_search(state: ChatTurnState):
        return await node_research_search(state, manager)

    async def research_evaluate(state: ChatTurnState):
        return await node_research_evaluate(state, manager)

    async def apply_refetch(state: ChatTurnState):
        return await node_apply_refetch(state, manager)

    async def expand_media(state: ChatTurnState):
        return await node_expand_media(state, manager)

    async def infer(state: ChatTurnState):
        return await node_infer(state, manager)

    async def synthesize(state: ChatTurnState):
        return await node_synthesize(state, manager)

    graph.add_node("prepare", prepare)
    graph.add_node("research_search", research_search)
    graph.add_node("research_evaluate", research_evaluate)
    graph.add_node("apply_refetch", apply_refetch)
    graph.add_node("expand_media", expand_media)
    graph.add_node("infer", infer)
    graph.add_node("synthesize", synthesize)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "research_search")
    graph.add_edge("research_search", "research_evaluate")
    graph.add_conditional_edges(
        "research_evaluate",
        route_after_evaluate,
        {
            "apply_refetch": "apply_refetch",
            "expand_media": "expand_media",
        },
    )
    graph.add_edge("apply_refetch", "research_search")
    graph.add_edge("expand_media", "infer")
    graph.add_edge("infer", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


__all__ = [
    "ChatTurnState",
    "apply_refetch_hint",
    "build_chat_graph",
    "build_synthesize_prompt",
    "merge_evidence",
    "should_refetch",
]
