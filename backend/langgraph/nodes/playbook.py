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
            stage="Playbook 执行",
            summary=f"进入 playbook 路径：{runtime_state.matched_playbook_id}",
            detail=str(playbook.get("detail", "命中固定经验流程，跳过知识库兜底路径。")),
        )
    )
    return {
        "runtime_state": runtime_state,
    }
