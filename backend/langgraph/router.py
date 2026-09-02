from __future__ import annotations

from backend.gateway.models import ChatRequest
from backend.langgraph.state import ChatGraphState


def select_route(*, matched_playbook_id: str, request: ChatRequest, interaction_mode: str = "agent") -> str:
    normalized_mode = str(interaction_mode or "").strip().lower()
    if matched_playbook_id:
        if normalized_mode == "qa":
            return "knowledge"
        return "playbook"
    if normalized_mode == "playbook":
        return "playbook_only"
    if request.content.strip():
        return "knowledge"
    return "idle"


def route_after_match(state: ChatGraphState) -> str:
    interaction_mode = str(state["runtime_state"].interaction_mode_snapshot or "").strip().lower()
    if str(state["runtime_state"].matched_playbook_id or "").strip():
        if interaction_mode in {"playbook", "agent"}:
            return "playbook_execution"
        return "knowledge_selection"
    if interaction_mode == "playbook":
        return "summarize_response"
    return "knowledge_selection"


def route_after_knowledge_mode(state: ChatGraphState) -> str:
    response_mode = str(state.get("response_mode") or "").strip().lower()
    if response_mode == "answer":
        return "build_messages"
    if response_mode == "clarify":
        return "summarize_response"
    return "build_messages"


def route_after_build_messages(state: ChatGraphState) -> str:
    response_mode = str(state.get("response_mode") or "").strip().lower()
    if response_mode == "clarify":
        return "summarize_response"
    return "call_model"


def route_after_interpret(state: ChatGraphState) -> str:
    result_kind = str(state.get("result_kind") or "").strip().lower()
    loop_count = int(state.get("model_loop_count") or 0)
    if result_kind in {"final", "clarify", "confirmation"}:
        response_mode = str(state.get("response_mode") or "").strip().lower()
        if response_mode == "answer" and result_kind == "final":
            return "done"
        return "summarize"
    if loop_count >= 6:
        return "summarize"
    if result_kind == "tool_call":
        return "retry"
    return "retry"


def route_after_playbook_execution(state: ChatGraphState) -> str:
    return "summarize"


def route_after_tool_planning(state: ChatGraphState) -> str:
    if str(state.get("response_mode") or "").strip().lower() == "answer":
        return "solution_generation"
    planned_tools = state["runtime_state"].planned_tools
    if planned_tools:
        return "robot_check"
    return "problem_analysis"


def route_after_call_tools(state: ChatGraphState) -> str:
    if state.get("confirmation_request"):
        return "await_confirmation"
    if str(state.get("tool_iteration_status") or "").strip().lower() == "duplicate_target_blocked":
        return "summarize"
    return "call_model"
