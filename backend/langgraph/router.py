from __future__ import annotations

from backend.gateway.models import ChatRequest
from backend.langgraph.state import ChatGraphState


def select_route(*, matched_playbook_id: str, request: ChatRequest) -> str:
    if matched_playbook_id:
        return "playbook"
    if request.content.strip():
        return "knowledge"
    return "idle"


def route_after_match(state: ChatGraphState) -> str:
    if str(state["runtime_state"].matched_playbook_id or "").strip():
        return "playbook_execution"
    return "knowledge_selection"


def route_after_playbook_execution(state: ChatGraphState) -> str:
    runtime_state = state["runtime_state"]
    if runtime_state.current_step in {"waiting_confirm", "waiting_input"}:
        return "finish"
    if runtime_state.finished:
        return "finish"
    return "summarize"


def route_after_tool_planning(state: ChatGraphState) -> str:
    if str(state.get("response_mode") or "").strip().lower() == "answer":
        return "solution_generation"
    planned_tools = state["runtime_state"].planned_tools
    if planned_tools:
        return "robot_check"
    return "problem_analysis"


def route_after_interpret(state: ChatGraphState) -> str:
    result_kind = str(state.get("result_kind") or "").strip().lower()
    loop_count = int(state.get("model_loop_count") or 0)
    if result_kind in {"final", "clarify", "confirmation"}:
        return "finish"
    if loop_count >= 6:
        return "finish"
    if result_kind == "tool_call":
        return "call_tools"
    return "retry"


def route_after_call_tools(state: ChatGraphState) -> str:
    if state.get("confirmation_request"):
        return "await_confirmation"
    return "call_model"
