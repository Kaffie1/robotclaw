from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...infra.stores import TaskContext
from ...shared.runtime import upload_progress_manager
from .common import resolve_playbook_progress


def log_playbook_steps(ctx: TaskContext, playbook_result: dict[str, Any]) -> None:
    playbook_title = str(playbook_result.get("playbook_title") or playbook_result.get("playbook_id") or "workflow").strip()
    ctx.log(f"开始执行 workflow: {playbook_title}")
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = str(step.get("name") or step.get("tool_name") or "step").strip()
        status_text = "成功" if bool(step.get("passed")) else "失败"
        ctx.log(f"Workflow 步骤[{status_text}]: {step_name}")
    conclusion = str(playbook_result.get("conclusion") or "").strip()
    if conclusion:
        ctx.log(f"Workflow 结论: {conclusion}")


def first_failed_message(playbook_result: dict[str, Any]) -> str:
    for step in playbook_result.get("steps") or []:
        if isinstance(step, dict) and not bool(step.get("passed")):
            return str(step.get("failure_message") or step.get("output") or step.get("name") or "workflow 执行失败").strip()
    return str(playbook_result.get("conclusion") or playbook_result.get("next_action") or "workflow 执行失败").strip()


def build_workflow_status_reporter(
    ctx: TaskContext,
    *,
    upload_token: str,
    tool_context: dict[str, Any],
    total_bytes_getter: Callable[[dict[str, Any]], int | None],
    progress_transformer: Callable[[dict[str, str], dict[str, Any]], dict[str, str]] | None = None,
    log_pending_confirmation: bool = True,
) -> Callable[[dict[str, Any]], None]:
    state = {"last_path": "", "last_message": ""}

    def reporter(execution_snapshot: dict[str, Any]) -> None:
        pending_confirmation = execution_snapshot.get("pending_confirmation") if isinstance(execution_snapshot, dict) else None
        node_path = str((execution_snapshot or {}).get("active_node_path") or "").strip()
        active_node_message = str((execution_snapshot or {}).get("active_node_message") or "").strip()
        progress_info = resolve_playbook_progress(execution_snapshot)
        if callable(progress_transformer):
            progress_info = progress_transformer(progress_info, tool_context)
        message = str(progress_info.get("message") or active_node_message or "").strip()
        if isinstance(pending_confirmation, dict):
            pending_message = str(pending_confirmation.get("message") or "").strip()
            if log_pending_confirmation and pending_message and pending_message != state["last_message"]:
                ctx.log(f"Workflow 等待确认: {pending_message}")
                state["last_message"] = pending_message
            return
        if not message:
            return
        if node_path == state["last_path"] and message == state["last_message"]:
            return
        state["last_path"] = node_path
        state["last_message"] = message
        ctx.log(f"Workflow 执行中: {message}")
        total_bytes = total_bytes_getter(tool_context)
        phase = str(progress_info.get("phase") or "").strip()
        byte_phases = {"downloading_from_server", "uploading_to_robot"}
        reported_transferred_bytes: int | None
        reported_total_bytes: int | None
        if phase in byte_phases:
            reported_transferred_bytes = None
            reported_total_bytes = total_bytes
        elif phase == "installing" and total_bytes is not None:
            reported_transferred_bytes = total_bytes
            reported_total_bytes = total_bytes
        else:
            # Clear stale upload/download progress once the workflow moves into a non-byte phase.
            reported_transferred_bytes = 0
            reported_total_bytes = 0
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=reported_transferred_bytes,
            total_bytes=reported_total_bytes,
            phase=phase,
            message=message,
            step_name=progress_info["step_name"],
            step_label=progress_info["step_label"],
            done=False,
            owner_id="",
        )

    return reporter
