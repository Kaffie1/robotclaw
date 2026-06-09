from __future__ import annotations

from backend.runtime.models import EvidenceItem
from backend.runtime.models import RouteDecision


def enter_playbook_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    playbook = state["playbook"]
    short_memory = state["short_memory"]
    request = state["request"]

    resume_context = None
    if request.resume:
        confirmation_context = dict(short_memory.scratchpad.get("confirmation_context") or {})
        if confirmation_context:
            payload = confirmation_context.get("payload")
            resume_context = {
                "node_id": str(confirmation_context.get("node_path") or "").strip(),
                "user_response": request.content,
                "tool_result": dict(payload.get("tool_result") or {}) if isinstance(payload, dict) and isinstance(payload.get("tool_result"), dict) else None,
            }

    runtime_state.current_step = "playbook_execution"
    execution = state["playbook_engine"].execute(
        runtime_state.matched_playbook_id,
        tool_executor=state["tool_executor"],
        connected=state["connected"],
        context=dict(short_memory.scratchpad.get("playbook_context") or {}),
        resume=resume_context,
    )
    runtime_state.playbook_execution.playbook_id = runtime_state.matched_playbook_id
    runtime_state.playbook_execution.current_node_id = str(execution.get("current_node_id") or "entry")
    runtime_state.playbook_execution.completed_nodes = list(execution.get("completed_nodes") or [])
    runtime_state.playbook_execution.failed_nodes = list(execution.get("failed_nodes") or [])
    runtime_state.playbook_execution.passed = execution.get("passed")
    pending_confirmation = execution.get("pending_confirmation") or {}
    waiting_kind = str(pending_confirmation.get("kind") or "").strip().lower()
    runtime_state.playbook_execution.status = (
        "waiting_input" if waiting_kind == "input" else ("waiting_confirm" if pending_confirmation else ("completed" if execution.get("executed") else "failed"))
    )
    runtime_state.playbook_execution.waiting_input_field = str(((pending_confirmation.get("output") or {}) if isinstance(pending_confirmation.get("output"), dict) else {}).get("store_as") or "")
    short_memory.scratchpad["playbook_execution"] = execution
    short_memory.scratchpad["playbook_context"] = dict(execution.get("playbook_context") or {})
    short_memory.rule_results = list(execution.get("rule_results") or [])
    if pending_confirmation:
        short_memory.scratchpad["confirmation_context"] = pending_confirmation
    else:
        short_memory.scratchpad.pop("confirmation_context", None)
        short_memory.pending_confirmation = None
    runtime_state.trace.append(
        RouteDecision(
            stage="模板执行",
            summary=f"进入模板路径：{runtime_state.matched_playbook_id}",
            detail=str(
                execution.get("developer_detail")
                or execution.get("conclusion")
                or playbook.get("detail")
                or "当前请求命中了预设模板路径。"
            ),
        )
    )
    if pending_confirmation:
        runtime_state.current_step = "waiting_input" if waiting_kind == "input" else "waiting_confirm"
        return {
            "runtime_state": runtime_state,
            "diagnosis": diagnosis,
            "short_memory": short_memory,
            "playbook": {
                **dict(playbook),
                "execution": execution,
                "summary": str(playbook.get("summary") or execution.get("conclusion") or ""),
                "detail": str(execution.get("next_action") or playbook.get("detail") or ""),
            },
        }

    analysis = {
        "summary": str(execution.get("conclusion") or playbook.get("summary") or "排查流程已执行完成。").strip(),
        "detail": str(
            execution.get("next_action")
            or execution.get("developer_detail")
            or playbook.get("detail")
            or "请根据当前执行结果继续处理。"
        ).strip(),
    }
    short_memory.scratchpad["analysis"] = analysis
    short_memory.scratchpad["summary_source"] = "pending_llm"
    diagnosis.evidence.append(
        EvidenceItem(
            source="playbook",
            content=analysis["summary"] or analysis["detail"],
            confidence=0.85 if execution.get("executed") else 0.45,
        )
    )
    runtime_state.current_step = "problem_analysis"
    runtime_state.finished = False
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "analysis": analysis,
        "playbook": {
            **dict(playbook),
            "execution": execution,
            "summary": str(playbook.get("summary") or execution.get("conclusion") or ""),
            "detail": str(execution.get("next_action") or playbook.get("detail") or ""),
        },
    }
