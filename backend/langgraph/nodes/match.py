from __future__ import annotations

from backend.langgraph.router import select_route
from backend.playbook import PlaybookEngine
from backend.runtime.models import EvidenceItem, RouteDecision


def match_playbook(playbook_engine: PlaybookEngine, content: str) -> dict[str, str | float]:
    return playbook_engine.match(content)


def match_playbook_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    request = state["request"]

    runtime_state.current_step = "match_playbook"
    playbook = match_playbook(state["playbook_engine"], request.content)
    runtime_state.matched_playbook_id = str(playbook["id"])
    runtime_state.playbook_execution.playbook_id = runtime_state.matched_playbook_id
    runtime_state.playbook_execution.status = "matched" if runtime_state.matched_playbook_id else "fallback"
    runtime_state.route = select_route(matched_playbook_id=runtime_state.matched_playbook_id, request=request)
    short_memory.scratchpad["route_prompt"] = state["build_route_prompt"](request.content)
    runtime_state.trace.append(
        RouteDecision(
            stage="Playbook 匹配",
            summary=str(playbook["summary"]),
            detail=str(playbook["detail"]),
        )
    )
    if playbook["id"]:
        diagnosis.evidence.append(
            EvidenceItem(
                source="playbook",
                content=str(playbook["summary"]),
                confidence=float(playbook["confidence"]),
            )
        )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "playbook": playbook,
    }
