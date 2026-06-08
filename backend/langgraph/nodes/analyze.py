from __future__ import annotations

from backend.playbook import PlaybookEngine
from backend.runtime.models import RouteDecision


def analyze_problem(
    playbook_engine: PlaybookEngine,
    playbook_id: str,
    tool_results: list[dict],
    connected: bool,
) -> dict[str, str]:
    return playbook_engine.analyze(playbook_id, tool_results, connected)


def analyze_problem_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]

    runtime_state.current_step = "problem_analysis"
    analysis = analyze_problem(
        state["playbook_engine"],
        runtime_state.matched_playbook_id,
        short_memory.tool_results,
        state["connected"],
    )
    short_memory.rule_results = [analysis]
    runtime_state.trace.append(RouteDecision(stage="问题分析", summary=analysis["summary"], detail=analysis["detail"]))
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "analysis": analysis,
    }
