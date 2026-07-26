"""Build and compile the outline LangGraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from services.outline.graph.nodes import (
    node_generate_draft,
    node_mark_failed,
    node_repair_json,
    node_validate_schema,
    route_after_validate,
)
from services.outline.graph.state import OutlineState


def build_outline_graph():
    graph = StateGraph(OutlineState)
    graph.add_node("node_generate_draft", node_generate_draft)
    graph.add_node("node_validate_schema", node_validate_schema)
    graph.add_node("node_repair_json", node_repair_json)
    graph.add_node("node_mark_failed", node_mark_failed)

    graph.add_edge(START, "node_generate_draft")
    graph.add_edge("node_generate_draft", "node_validate_schema")
    graph.add_conditional_edges(
        "node_validate_schema",
        route_after_validate,
        {
            "done": END,
            "node_repair_json": "node_repair_json",
            "node_mark_failed": "node_mark_failed",
        },
    )
    graph.add_edge("node_repair_json", "node_validate_schema")
    graph.add_edge("node_mark_failed", END)
    return graph.compile()


_outline_graph = None


def get_outline_graph():
    global _outline_graph
    if _outline_graph is None:
        _outline_graph = build_outline_graph()
    return _outline_graph
