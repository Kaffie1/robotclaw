from __future__ import annotations

from backend.runtime.models import RouteDecision


def enter_playbook_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    playbook = state["playbook"]

    runtime_state.current_step = "playbook_execution"
    runtime_state.playbook_execution.current_node = "entry"
    runtime_state.playbook_execution.status = "running"
    runtime_state.trace.append(
        RouteDecision(
            stage="模板执行",
            summary=f"进入模板路径：{runtime_state.matched_playbook_id}",
            detail=str(playbook.get("detail", "当前请求命中了预设模板路径。")),
        )
    )
    return {
        "runtime_state": runtime_state,
    }
