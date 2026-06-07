from __future__ import annotations

import json
import uuid
from typing import Any

from ...core.config import OPENAI_CHAT_MODEL
from ...core.models import ApiError
from ...core.shared import append_fault_trace, extract_json_payload, logger, normalize_message_content, strip_think_blocks
from ...runtime.workflow.playbook_state import (
    build_matched_playbook_payload_by_id,
    build_playbook_execution_payload,
)
from ..graph.builder import get_chat_graph
from ..graph.timing import log_stage_duration, start_stage_timer
from ..shared.thread_context import (
    clear_runtime_tool_context,
    sanitize_tool_context,
    store_runtime_tool_context,
)

try:
    from langgraph.types import Command
except Exception:
    Command = None


def _format_loop_exit_message(result: dict[str, Any], fallback_message: str) -> str:
    parsed = result.get("parsed_response")
    if isinstance(parsed, dict):
        response_type = normalize_message_content(parsed.get("type") or parsed.get("mode") or "").lower()
        if response_type in {"final", "answer", "summary"}:
            answer = normalize_message_content(
                parsed.get("answer")
                or parsed.get("content")
                or parsed.get("summary")
                or parsed.get("message")
            )
            if answer:
                return answer
    if isinstance(parsed, dict):
        commands = parsed.get("commands")
        if isinstance(commands, list) and commands:
            first = commands[0] if isinstance(commands[0], dict) else {}
            tool_name = normalize_message_content(first.get("name") or first.get("tool_name") or "")
            tool_args = first.get("arguments") if isinstance(first.get("arguments"), dict) else {}
            lines = ["当前还在按恢复流程继续排查，但本轮自动执行已达到上限。"]
            if tool_name:
                lines.append(f"建议下一步工具：{tool_name}")
            if tool_args:
                arg_text = ", ".join(f"{key}={value}" for key, value in tool_args.items())
                if arg_text:
                    lines.append(f"建议参数：{arg_text}")
            return "\n".join(lines).strip()
    fallback_payload = extract_json_payload(fallback_message)
    if isinstance(fallback_payload, dict):
        response_type = normalize_message_content(
            fallback_payload.get("type") or fallback_payload.get("mode") or ""
        ).lower()
        if response_type in {"final", "answer", "summary"}:
            answer = normalize_message_content(
                fallback_payload.get("answer")
                or fallback_payload.get("content")
                or fallback_payload.get("summary")
                or fallback_payload.get("message")
            )
            if answer:
                return answer
            try:
                return json.dumps(fallback_payload, ensure_ascii=False, indent=2)
            except Exception:  # noqa: BLE001
                pass
    return fallback_message


def _build_invoke_input(
    *,
    user_message: str,
    thread_id: str,
    runtime_context: dict[str, Any] | None,
    tool_context: dict[str, Any] | None,
    conversation_history: list[dict[str, str]] | None,
    resume_continuation: dict[str, Any] | None,
    confirmation_response: str,
    prefetched_playbook_id: str,
    prefetched_playbook_title: str,
    prefetched_playbook_type: str,
    prefetched_reason: str,
) -> dict[str, Any]:
    store_runtime_tool_context(thread_id, tool_context)
    sanitized_tool_context = sanitize_tool_context(tool_context)
    return {
        "thread_id": thread_id,
        "session_id": normalize_message_content((tool_context or {}).get("session_id", "")),
        "user_message": normalize_message_content(user_message),
        "conversation_history": list(conversation_history or [])[:10],
        "runtime_context": runtime_context or {},
        "tool_context": sanitized_tool_context,
        "effective_tool_context": dict(sanitized_tool_context),
        "tool_traces": [],
        "model_loop_count": 0,
        "resume_continuation": dict(resume_continuation or {}) if isinstance(resume_continuation, dict) else None,
        "confirmation_response": normalize_message_content(confirmation_response),
        "prefetched_playbook_id": normalize_message_content(prefetched_playbook_id),
        "prefetched_playbook_title": normalize_message_content(prefetched_playbook_title),
        "prefetched_playbook_type": normalize_message_content(prefetched_playbook_type).lower(),
        "prefetched_reason": normalize_message_content(prefetched_reason),
    }


def run_fault_chat_graph(
    user_message: str,
    *,
    runtime_context: dict[str, Any] | None = None,
    tool_context: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    resume_continuation: dict[str, Any] | None = None,
    confirmation_response: str = "",
    prefetched_playbook_id: str = "",
    prefetched_playbook_title: str = "",
    prefetched_playbook_type: str = "",
    prefetched_reason: str = "",
) -> dict[str, Any]:
    started_at = start_stage_timer()
    chat_graph = get_chat_graph()
    if chat_graph is None:
        raise ApiError("聊天图依赖未安装，请先安装 langgraph")
    continuation_kind = normalize_message_content((resume_continuation or {}).get("kind", "")) if isinstance(resume_continuation, dict) else ""
    thread_id = normalize_message_content((resume_continuation or {}).get("thread_id", "")) if isinstance(resume_continuation, dict) else ""
    if not thread_id:
        thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    if continuation_kind == "playbook_render_ready" and Command is not None:
        invoke_input: Any = Command(resume=True)
    else:
        invoke_input = _build_invoke_input(
            user_message=user_message,
            thread_id=thread_id,
            runtime_context=runtime_context,
            tool_context=tool_context,
            conversation_history=conversation_history,
            resume_continuation=resume_continuation,
            confirmation_response=confirmation_response,
            prefetched_playbook_id=prefetched_playbook_id,
            prefetched_playbook_title=prefetched_playbook_title,
            prefetched_playbook_type=prefetched_playbook_type,
            prefetched_reason=prefetched_reason,
        )
    result = chat_graph.invoke(invoke_input, config=config)
    selected_playbook_type = normalize_message_content(result.get("selected_playbook_type", "")).lower()
    matched_playbook = build_matched_playbook_payload_by_id(
        result.get("selected_playbook_id", ""),
        workflow_type=selected_playbook_type or None,
    )
    playbook_execution = build_playbook_execution_payload(
        result.get("scripted_playbook"),
        pending_confirmation=result.get("pending_confirmation"),
    )
    interrupts = result.get("__interrupt__")
    if isinstance(interrupts, (list, tuple)) and interrupts:
        interrupt_item = interrupts[0]
        pending_playbook_render = getattr(interrupt_item, "value", None)
        continuation = {
            "kind": "playbook_render_ready",
            "user_message": normalize_message_content(user_message),
            "playbook_id": normalize_message_content(result.get("selected_playbook_id", "")),
            "playbook_type": selected_playbook_type,
            "playbook_title": normalize_message_content(result.get("selected_playbook_title", "")),
            "reason": normalize_message_content(result.get("reason", "")),
            "thread_id": thread_id,
        }
        logger.info("=== Chat 中断 (playbook_render_wait) | playbook=%s", continuation["playbook_id"] or "-")
        log_stage_duration("run_fault_chat_graph", started_at, result="playbook_render_wait")
        return {
            "model": OPENAI_CHAT_MODEL,
            "message": normalize_message_content(pending_playbook_render.get("message", "")) or "等待前端流程图加载完成",
            "tool_traces": result.get("tool_traces") or [],
            "continuation": continuation,
            "playbook": pending_playbook_render.get("playbook"),
            "playbook_execution": playbook_execution,
        }
    pending_confirmation = result.get("pending_confirmation")
    if isinstance(pending_confirmation, dict):
        continuation = {
            "kind": "playbook_confirmation",
            "user_message": normalize_message_content(user_message),
            "thread_id": thread_id,
            "playbook_id": normalize_message_content(result.get("selected_playbook_id", "")),
            "playbook_type": selected_playbook_type,
            "playbook_title": normalize_message_content(result.get("selected_playbook_title", "")),
            "reason": normalize_message_content(result.get("reason", "")),
            "tool_context": sanitize_tool_context(result.get("effective_tool_context")),
            "resume_state": result.get("playbook_resume_state") if isinstance(result.get("playbook_resume_state"), dict) else {},
            "pending_confirmation": pending_confirmation,
        }
        logger.info(
            "=== Chat 中断 (confirmation) | playbook=%s | 工具调用次数: %d",
            continuation["playbook_id"] or "-",
            len(result.get("tool_traces") or []),
        )
        log_stage_duration("run_fault_chat_graph", started_at, result="confirmation")
        return {
            "model": OPENAI_CHAT_MODEL,
            "message": normalize_message_content(pending_confirmation.get("message", "")) or "需要人工确认后继续",
            "tool_traces": result.get("tool_traces") or [],
            "pending_confirmation": pending_confirmation,
            "continuation": continuation,
            "playbook": matched_playbook,
            "playbook_execution": playbook_execution,
        }
    final_message = normalize_message_content(result.get("final_message", ""))
    if final_message:
        clear_runtime_tool_context(thread_id)
        logger.info("=== Chat 结束 (%s) | 工具调用次数: %d", result.get("result_kind") or "final", len(result.get("tool_traces") or []))
        log_stage_duration(
            "run_fault_chat_graph",
            started_at,
            result=result.get("result_kind") or "final",
            tool_trace_count=len(result.get("tool_traces") or []),
        )
        return {
            "model": OPENAI_CHAT_MODEL,
            "message": final_message,
            "tool_traces": result.get("tool_traces") or [],
            "playbook": matched_playbook,
            "playbook_execution": playbook_execution,
        }
    response = result.get("response")
    content = getattr(response, "content", "")
    normalized_content = normalize_message_content(strip_think_blocks(str(content)))
    if not normalized_content:
        raise ApiError("模型未返回有效内容")
    append_fault_trace(
        "chat_final",
        {
            "type": "loop_exit",
            "message": normalized_content,
            "tool_traces": result.get("tool_traces") or [],
        },
    )
    logger.warning("=== Chat 结束 (loop_exit) | 达到最大循环次数 | 工具调用次数: %d", len(result.get("tool_traces") or []))
    user_facing_message = _format_loop_exit_message(result, normalized_content)
    clear_runtime_tool_context(thread_id)
    log_stage_duration(
        "run_fault_chat_graph",
        started_at,
        result="loop_exit",
        tool_trace_count=len(result.get("tool_traces") or []),
    )
    return {
        "model": OPENAI_CHAT_MODEL,
        "message": user_facing_message,
        "tool_traces": result.get("tool_traces") or [],
        "playbook": matched_playbook,
        "playbook_execution": playbook_execution,
    }
