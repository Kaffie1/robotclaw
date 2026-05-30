from __future__ import annotations

import json
from typing import Any

from ....core.models import ApiError
from ....core.shared import (
    append_fault_trace,
    logger,
    normalize_message_content,
)
from ....runtime.playbooks import run_scripted_playbook_by_id
from ....runtime.tools import tool_registry
from ....runtime.workflow.confirmation import apply_confirmation_response
from ....runtime.workflow.playbook_state import build_matched_playbook_payload, publish_live_playbook_state
from ...prompts.answer import build_playbook_summary_prompt
from ...shared.model_factory import load_chat_message_classes
from ...shared.thread_context import hydrate_runtime_tool_context, sanitize_tool_context
from ..state import FaultChatState
from .answer import _find_selected_playbook


def _build_tool_feedback_message(tool_name: str, tool_args: dict[str, Any], tool_result: dict[str, Any]) -> str:
    return (
        "【工具执行结果】\n"
        f"工具: {tool_name}\n"
        f"参数: {json.dumps(tool_args, ensure_ascii=False)}\n"
        f"结果: {json.dumps(tool_result, ensure_ascii=False)}"
    )


def _extend_tool_traces_from_script(tool_traces: list[dict[str, Any]], scripted_playbook: dict[str, Any]) -> None:
    if not isinstance(scripted_playbook, dict):
        return
    for step in scripted_playbook.get("steps") or []:
        if isinstance(step, dict):
            tool_traces.append(
                {
                    "name": step.get("name", ""),
                    "arguments": step.get("arguments", {}),
                    "result": step.get("output", ""),
                }
            )
    for nested_playbook in scripted_playbook.get("sub_playbooks") or []:
        _extend_tool_traces_from_script(tool_traces, nested_playbook)
    nested_playbook = scripted_playbook.get("sub_playbook")
    if isinstance(nested_playbook, dict):
        _extend_tool_traces_from_script(tool_traces, nested_playbook)


def _build_playbook_final_message(state: FaultChatState, scripted_playbook: dict[str, Any]) -> dict[str, Any]:
    playbook_title = normalize_message_content(
        scripted_playbook.get("playbook_title")
        or state.get("selected_playbook_title")
        or state.get("selected_playbook_id")
        or "故障流程"
    )
    user_message = normalize_message_content(state.get("user_message", ""))
    conclusion = normalize_message_content(scripted_playbook.get("conclusion", ""))
    next_action = normalize_message_content(scripted_playbook.get("next_action", ""))
    steps = [step for step in (scripted_playbook.get("steps") or []) if isinstance(step, dict)]

    process_lines: list[str] = []
    for index, step in enumerate(steps, start=1):
        name = normalize_message_content(
            step.get("display_name") or step.get("name") or step.get("tool_name") or f"步骤{index}"
        )
        outcome = "成功" if bool(step.get("passed")) else "失败"
        detail = normalize_message_content(step.get("output") or step.get("failure_message") or "")
        line = f"{index}. {name}：{outcome}"
        if detail:
            line += f"；{detail}"
        process_lines.append(line)

    if not process_lines:
        process_lines.append("1. 已执行脚本化排查流程，未记录到可展示的步骤明细。")

    problem = user_message or f"{playbook_title}相关问题"
    if not conclusion:
        conclusion = "流程已执行完成，但未生成明确结论。"
    if next_action and next_action != conclusion:
        conclusion = f"{conclusion}\n建议下一步：{next_action}"

    return {
        "problem": problem,
        "process": process_lines,
        "conclusion": conclusion,
        "playbook_title": playbook_title,
    }


def _build_playbook_summary_request(state: FaultChatState, scripted_playbook: dict[str, Any]) -> str:
    return build_playbook_summary_prompt(
        _build_playbook_final_message(state, scripted_playbook),
        scripted_playbook,
    )


def execute_playbook_node(state: FaultChatState) -> FaultChatState:
    selected_playbook_id = normalize_message_content(state.get("selected_playbook_id", ""))
    if not selected_playbook_id:
        return {
            "scripted_playbook": None,
            "pending_confirmation": None,
            "playbook_resume_state": None,
        }
    thread_id = normalize_message_content(state.get("thread_id", ""))
    session_id = normalize_message_content(state.get("session_id", ""))
    selected_playbook = _find_selected_playbook(selected_playbook_id)
    matched_playbook_payload = build_matched_playbook_payload(selected_playbook)
    resume_continuation = state.get("resume_continuation")
    continuation_kind = normalize_message_content((resume_continuation or {}).get("kind", "")) if isinstance(resume_continuation, dict) else ""
    if continuation_kind != "playbook_confirmation":
        publish_live_playbook_state(session_id=session_id, playbook=matched_playbook_payload)
    else:
        logger.info("人工确认恢复时保留当前流程图状态，不发送空执行状态 | playbook_id=%s", selected_playbook_id)
    effective_tool_context = hydrate_runtime_tool_context(thread_id, state.get("effective_tool_context"))
    resume_state = None
    if isinstance(resume_continuation, dict):
        effective_tool_context = apply_confirmation_response(
            effective_tool_context,
            resume_continuation.get("pending_confirmation"),
            normalize_message_content(state.get("confirmation_response", "")),
        )
        raw_resume_state = resume_continuation.get("resume_state")
        resume_state = raw_resume_state if isinstance(raw_resume_state, dict) else None
    logger.info(
        "执行 playbook 前检查恢复态 | playbook_id=%s | continuation_kind=%s | has_resume_state=%s | resume_completed_nodes=%s",
        selected_playbook_id,
        continuation_kind,
        isinstance(resume_state, dict),
        sorted(str(key) for key in (resume_state.get("completed_nodes") or {}).keys()) if isinstance(resume_state, dict) and isinstance(resume_state.get("completed_nodes"), dict) else [],
    )
    scripted_playbook = run_scripted_playbook_by_id(
        selected_playbook_id,
        effective_tool_context,
        workflow_type="fault",
        resume_state=resume_state,
        status_reporter=lambda payload: publish_live_playbook_state(
            session_id=session_id,
            playbook=matched_playbook_payload,
            scripted_playbook=payload,
            pending_confirmation=payload.get("pending_confirmation") if isinstance(payload, dict) else None,
            active_node_path=normalize_message_content((payload or {}).get("active_node_path", "")),
            active_node_message=normalize_message_content((payload or {}).get("active_node_message", "")),
        ),
    )
    if not scripted_playbook:
        return {
            "scripted_playbook": None,
            "pending_confirmation": None,
            "playbook_resume_state": None,
        }
    append_fault_trace("playbook_script", scripted_playbook)
    tool_traces = list(state.get("tool_traces") or [])
    _extend_tool_traces_from_script(tool_traces, scripted_playbook)
    if isinstance(scripted_playbook.get("pending_confirmation"), dict):
        pending_confirmation = scripted_playbook.get("pending_confirmation")
        publish_live_playbook_state(
            session_id=session_id,
            playbook=matched_playbook_payload,
            scripted_playbook=scripted_playbook,
            pending_confirmation=pending_confirmation,
            active_node_path=normalize_message_content(pending_confirmation.get("node_path", "")),
            active_node_message=normalize_message_content(pending_confirmation.get("message", "")),
        )
        append_fault_trace("playbook_confirmation", pending_confirmation)
        return {
            "scripted_playbook": scripted_playbook,
            "tool_traces": tool_traces,
            "effective_tool_context": sanitize_tool_context(effective_tool_context),
            "pending_confirmation": pending_confirmation,
            "playbook_resume_state": scripted_playbook.get("resume_state"),
            "final_message": normalize_message_content(pending_confirmation.get("message", "")),
            "result_kind": "confirmation",
        }
    messages = list(state.get("messages") or [])
    _, HumanMessage, _ = load_chat_message_classes()
    messages.append(HumanMessage(content=_build_playbook_summary_request(state, scripted_playbook)))
    publish_live_playbook_state(
        session_id=session_id,
        playbook=matched_playbook_payload,
        scripted_playbook=scripted_playbook,
    )
    return {
        "scripted_playbook": scripted_playbook,
        "tool_traces": tool_traces,
        "effective_tool_context": sanitize_tool_context(effective_tool_context),
        "pending_confirmation": None,
        "playbook_resume_state": None,
        "messages": messages,
        "playbook_completed": bool(scripted_playbook.get("executed")),
        "final_message": "",
        "result_kind": "",
    }


def call_tools_node(state: FaultChatState) -> FaultChatState:
    thread_id = normalize_message_content(state.get("thread_id", ""))
    messages = list(state.get("messages") or [])
    tool_traces = list(state.get("tool_traces") or [])
    effective_tool_context = hydrate_runtime_tool_context(thread_id, state.get("effective_tool_context"))
    _, HumanMessage, _ = load_chat_message_classes()
    for command in state.get("pending_commands") or []:
        tool_name = str(command.get("name") or command.get("tool_name") or "").strip()
        if not tool_name:
            raise ApiError("模型输出的命令缺少工具名")
        tool_args = command.get("arguments")
        if not isinstance(tool_args, dict):
            tool_args = command.get("args") if isinstance(command.get("args"), dict) else {}
        append_fault_trace("tool_call_start", {"name": tool_name, "arguments": tool_args})
        logger.info("🔧 执行工具: %s, 参数: %s", tool_name, json.dumps(tool_args, ensure_ascii=False))
        try:
            tool_result = tool_registry.call_tool(tool_name, tool_args, effective_tool_context)
            tool_traces.append({"name": tool_name, "arguments": tool_args, "result": tool_result})
            append_fault_trace("tool_call", {"name": tool_name, "arguments": tool_args, "result": tool_result})
            logger.info("✅ 工具执行成功: %s", tool_name)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = exc.message if isinstance(exc, ApiError) else str(exc)
            tool_result = {"ok": False, "error": error_message}
            tool_traces.append({"name": tool_name, "arguments": tool_args, "error": error_message})
            append_fault_trace("tool_call_error", {"name": tool_name, "arguments": tool_args, "error": error_message})
            logger.error("❌ 工具执行失败: %s, 错误: %s", tool_name, error_message)
        append_fault_trace(
            "tool_call_end",
            {
                "name": tool_name,
                "arguments": tool_args,
                "ok": bool(tool_result.get("ok", True)) if isinstance(tool_result, dict) else True,
            },
        )
        messages.append(HumanMessage(content=_build_tool_feedback_message(tool_name, tool_args, tool_result)))
    return {
        "messages": messages,
        "tool_traces": tool_traces,
        "pending_commands": [],
        "effective_tool_context": sanitize_tool_context(effective_tool_context),
    }


__all__ = ["call_tools_node", "execute_playbook_node"]
