from __future__ import annotations

from typing import Any

from .nodes.answer import build_messages_node, call_chat_model_node, interpret_model_output_node
from .nodes.classify import load_catalog_node
from .nodes.execute import call_tools_node, execute_playbook_node
from .router import route_after_interpret_node, route_after_playbook_node, route_playbook_node, wait_for_playbook_render_node
from .state import FaultChatState

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:
    InMemorySaver = None

try:
    from langgraph.graph import END, StateGraph
except Exception:
    END = None
    StateGraph = None


def build_graph() -> Any:
    if StateGraph is None or END is None:
        return None
    graph = StateGraph(FaultChatState)
    graph.add_node("load_catalog", load_catalog_node)
    graph.add_node("route_playbook", route_playbook_node)
    graph.add_node("wait_playbook_render", wait_for_playbook_render_node)
    graph.add_node("build_messages", build_messages_node)
    graph.add_node("execute_playbook", execute_playbook_node)
    graph.add_node("call_model", call_chat_model_node)
    graph.add_node("interpret_output", interpret_model_output_node)
    graph.add_node("call_tools", call_tools_node)
    graph.set_entry_point("load_catalog")
    graph.add_edge("load_catalog", "route_playbook")
    graph.add_edge("route_playbook", "wait_playbook_render")
    graph.add_edge("wait_playbook_render", "build_messages")
    graph.add_edge("build_messages", "execute_playbook")
    graph.add_conditional_edges(
        "execute_playbook",
        route_after_playbook_node,
        {
            "finish": END,
            "call_model": "call_model",
        },
    )
    graph.add_edge("call_model", "interpret_output")
    graph.add_conditional_edges(
        "interpret_output",
        route_after_interpret_node,
        {
            "finish": END,
            "loop_exit": END,
            "retry": "call_model",
            "tool_call": "call_tools",
        },
    )
    graph.add_edge("call_tools", "call_model")
    compile_kwargs: dict[str, Any] = {}
    if InMemorySaver is not None:
        compile_kwargs["checkpointer"] = InMemorySaver()
    return graph.compile(**compile_kwargs)


_CHAT_GRAPH: Any = None


def get_chat_graph() -> Any:
    global _CHAT_GRAPH
    if _CHAT_GRAPH is None:
        _CHAT_GRAPH = build_graph()
    return _CHAT_GRAPH


__all__ = ["build_graph", "get_chat_graph"]
