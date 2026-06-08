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


def route_after_tool_planning(state: ChatGraphState) -> str:
    planned_tools = state["runtime_state"].planned_tools
    if planned_tools:
        return "robot_check"
    return "problem_analysis"
