"""LangGraph 条件路由规则。

统一承接图内的条件分支判断，以及与路由节点相关的公共入口。
节点本身仍放在 `graph/nodes/route.py`，但“下一跳怎么选”放在这里，
这样结构会更接近上级 knowledge 项目的拆分方式。
"""

from .nodes.route import (
    resolve_playbook_route,
    route_playbook_node,
    wait_for_playbook_render_node,
)
from .state import FaultChatState


def route_after_route_playbook_node(state: FaultChatState) -> str:
    if str(state.get("selected_playbook_id") or "").strip():
        return "wait_playbook_render"
    return "build_messages"


def route_after_build_messages_node(state: FaultChatState) -> str:
    if str(state.get("selected_playbook_id") or "").strip():
        return "execute_playbook"
    return "retrieve_knowledge"


def route_after_playbook_node(state: FaultChatState) -> str:
    if isinstance(state.get("pending_confirmation"), dict):
        return "finish"
    return "call_model"


def route_after_interpret_node(state: FaultChatState) -> str:
    result_kind = str(state.get("result_kind") or "")
    loop_count = int(state.get("model_loop_count") or 0)
    if result_kind in {"final", "clarify"}:
        return "finish"
    if loop_count >= 6:
        return "loop_exit"
    if result_kind == "tool_call":
        return "tool_call"
    return "retry"

__all__ = [
    "resolve_playbook_route",
    "route_after_build_messages_node",
    "route_after_route_playbook_node",
    "route_after_interpret_node",
    "route_after_playbook_node",
    "route_playbook_node",
    "wait_for_playbook_render_node",
]
