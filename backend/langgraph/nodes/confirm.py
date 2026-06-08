from __future__ import annotations

from dataclasses import asdict

from backend.runtime.models import RouteDecision
from backend.runtime.workflow import build_confirmation_request


def await_confirmation_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    request = state["request"]
    confirmation_context = short_memory.scratchpad.get("confirmation_context") or {}
    resume_from_step = str(runtime_state.resume_from_step or confirmation_context.get("resume_from_step") or "tool_planning").strip()
    node_path = str(confirmation_context.get("node_path") or "tool_planning/connect_robot").strip()
    message = str(
        confirmation_context.get("message")
        or "当前需要先建立外部连接，连接完成后再继续执行工具动作。"
    ).strip()
    options = confirmation_context.get("options")
    if not isinstance(options, list) or not options:
        options = ["已完成连接，继续执行"]

    runtime_state.current_step = "waiting_confirm"
    runtime_state.finished = False
    runtime_state.resume_from_step = resume_from_step
    confirmation = build_confirmation_request(
        request_id=request.request_id,
        session_id=runtime_state.session_id,
        task_id=runtime_state.task_id,
        node_path=node_path,
        message=message,
        options=options,
        resume_from_step=runtime_state.resume_from_step,
        payload={
            "planned_tools": [item.tool_name for item in runtime_state.planned_tools],
            "reason": "robot_connection_required",
        },
    )
    state["workflow_store"].save_confirmation(confirmation)
    short_memory.pending_confirmation = asdict(confirmation)
    runtime_state.trace.append(
        RouteDecision(
            stage="人工确认",
            summary="等待外部连接完成后继续执行",
            detail="当前工具规划依赖外部连接条件，已挂起执行并生成恢复入口。",
        )
    )
    analysis = {
        "summary": "当前流程等待人工确认后继续执行",
        "detail": "工具规划已完成，但由于外部连接条件尚未满足，执行在确认节点挂起，等待连接完成后继续。",
    }
    short_memory.rule_results = [analysis]
    short_memory.scratchpad["analysis"] = analysis
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "analysis": analysis,
        "confirmation_request": confirmation,
    }
