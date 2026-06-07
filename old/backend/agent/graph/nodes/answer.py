from __future__ import annotations

import json
from typing import Any

from ....core.config import OPENAI_CHAT_MODEL
from ....core.models import ApiError
from ....core.shared import (
    append_fault_trace,
    extract_json_payload,
    logger,
    normalize_message_content,
    strip_think_blocks,
)
from ....runtime.playbooks import build_fault_doc_context_from_playbook, list_playbooks
from ....runtime.tools import tool_registry
from ...prompts.answer import build_fault_chat_system_prompt, build_knowledge_answer_system_prompt
from ...shared.model_factory import build_chat_model, invoke_chat_model, load_chat_message_classes
from ..state import FaultChatState
from ..timing import log_stage_duration, start_stage_timer


def _coerce_structured_text(value: Any) -> Any:
    import ast

    if isinstance(value, (dict, list)):
        return value
    text = normalize_message_content(value)
    if not text:
        return text
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return text


def _normalize_final_answer(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = normalize_message_content(raw_key)
        compact_key = key.replace("：", "").replace(":", "").replace(" ", "")
        if compact_key == "问题":
            normalized["问题："] = raw_value
        elif compact_key in {"排查过程", "分析过程", "处理过程"}:
            normalized["排查过程："] = raw_value
        elif compact_key in {"结论", "结果", "建议"}:
            normalized["结论："] = raw_value
    return normalized if "结论：" in normalized else None


def _render_polished_final_answer(answer: dict[str, Any]) -> str:
    conclusion = normalize_message_content(answer.get("结论：", ""))
    return conclusion


def _render_final_message(value: Any) -> str:
    structured = _coerce_structured_text(value)
    if isinstance(structured, dict):
        normalized_answer = _normalize_final_answer(structured)
        if normalized_answer is not None:
            return _render_polished_final_answer(normalized_answer)
        return json.dumps(structured, ensure_ascii=False, indent=2)
    if isinstance(structured, list):
        return "\n".join(
            f"- {normalize_message_content(item)}"
            for item in structured
            if normalize_message_content(item)
        ).strip()
    return strip_think_blocks(normalize_message_content(structured)).replace("\\n", "\n").replace("\\t", "\t")


def _extract_final_message(payload: dict[str, Any], fallback_text: str) -> str:
    nested_final = payload.get("final") if isinstance(payload.get("final"), dict) else {}
    for candidate in (
        payload.get("answer"),
        nested_final.get("answer"),
        nested_final.get("content"),
        nested_final.get("summary"),
        nested_final.get("message"),
        payload.get("content"),
        payload.get("summary"),
        payload.get("message"),
        fallback_text,
    ):
        text = _render_final_message(candidate)
        if text:
            return text
    return ""


def _final_message_has_required_sections(message: str) -> bool:
    text = normalize_message_content(message)
    return bool(text)


def _format_message_log(messages: list[Any]) -> str:
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = str(getattr(message, "type", "") or message.__class__.__name__).replace("Message", "").lower()
        content = normalize_message_content(getattr(message, "content", ""))
        lines.append(f"[{index}] {role}")
        lines.append(content or "-")
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_response_log(response: Any) -> str:
    content = normalize_message_content(getattr(response, "content", ""))
    response_type = str(getattr(response, "type", "") or response.__class__.__name__).strip()
    lines = [f"type: {response_type}"]
    if content:
        lines.append("content:")
        lines.append(content)
    else:
        lines.append("content: -")
    return "\n".join(lines)


def _extract_usage_stats(response: Any) -> dict[str, int]:
    usage_sources = []
    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        usage_sources.append(usage_metadata)
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage")
        if isinstance(token_usage, dict):
            usage_sources.append(token_usage)
        usage = response_metadata.get("usage")
        if isinstance(usage, dict):
            usage_sources.append(usage)

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    for source in usage_sources:
        prompt_tokens = max(
            prompt_tokens,
            int(source.get("input_tokens") or source.get("prompt_tokens") or 0),
        )
        completion_tokens = max(
            completion_tokens,
            int(source.get("output_tokens") or source.get("completion_tokens") or 0),
        )
        total_tokens = max(
            total_tokens,
            int(source.get("total_tokens") or 0),
        )
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _normalize_command_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    raw_commands = payload.get("commands")
    if isinstance(raw_commands, list):
        for item in raw_commands:
            if isinstance(item, dict):
                commands.append(item)
    elif isinstance(raw_commands, dict):
        commands.append(raw_commands)
    elif payload.get("name") or payload.get("tool_name"):
        commands.append(payload)
    return commands


def _format_clarify_item(item: Any) -> str:
    if isinstance(item, str):
        return normalize_message_content(item)
    if isinstance(item, dict):
        question = normalize_message_content(
            item.get("question")
            or item.get("content")
            or item.get("title")
            or item.get("message")
        )
        options = item.get("options")
        lines: list[str] = []
        if question:
            lines.append(question)
        if isinstance(options, list):
            for option in options:
                if isinstance(option, dict):
                    option_text = normalize_message_content(
                        option.get("display_label")
                        or option.get("label")
                        or option.get("text")
                        or option.get("value")
                        or option.get("name")
                    )
                else:
                    option_text = normalize_message_content(option)
                if option_text:
                    lines.append(f"- {option_text}")
        return "\n".join(lines).strip()
    return normalize_message_content(item)


def _build_chat_messages(user_message: str, *, fault_doc_context: str = "") -> list[Any]:
    AIMessage, HumanMessage, SystemMessage = load_chat_message_classes()
    normalized_user_message = normalize_message_content(user_message)
    if not normalized_user_message:
        raise ApiError("聊天内容不能为空")
    tool_definitions = tool_registry.list_definitions()
    system_prompt = build_fault_chat_system_prompt(tool_definitions)
    if fault_doc_context:
        system_prompt = f"{system_prompt}\n\n{fault_doc_context}"
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=normalized_user_message),
    ]


def _append_history_messages(messages: list[Any], history: list[dict[str, str]] | None) -> list[Any]:
    if not isinstance(history, list) or not history:
        return messages
    AIMessage, HumanMessage, _ = load_chat_message_classes()
    normalized_history: list[Any] = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = normalize_message_content(item.get("role", "")).lower()
        content = normalize_message_content(item.get("content", ""))
        if not content:
            continue
        if role == "assistant":
            normalized_history.append(AIMessage(content=content))
        elif role == "user":
            normalized_history.append(HumanMessage(content=content))
    if len(messages) < 2:
        return messages + normalized_history
    return [messages[0], *normalized_history, messages[-1]]


def _find_selected_playbook(selected_playbook_id: str, selected_playbook_type: str = "") -> dict[str, Any] | None:
    normalized_playbook_id = normalize_message_content(selected_playbook_id)
    normalized_playbook_type = normalize_message_content(selected_playbook_type).lower()
    if not normalized_playbook_id:
        return None
    for playbook in list_playbooks(workflow_type=normalized_playbook_type or None):
        if normalize_message_content(playbook.get("id", "")) == normalized_playbook_id:
            return playbook
    return None


def build_messages_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    user_message = normalize_message_content(state.get("user_message", ""))
    selected_playbook_id = normalize_message_content(state.get("selected_playbook_id", ""))
    selected_playbook_title = normalize_message_content(state.get("selected_playbook_title", ""))
    selected_playbook_type = normalize_message_content(state.get("selected_playbook_type", ""))
    reason = normalize_message_content(state.get("reason", ""))
    route_trace = {
        "playbook_id": selected_playbook_id,
        "playbook_title": selected_playbook_title,
        "playbook_type": selected_playbook_type,
        "reason": reason,
    }
    logger.info("开始故障路由 | user_message=%s", user_message[:120])
    append_fault_trace("route_start", {"user_message": user_message})
    append_fault_trace("route_finish", route_trace)
    selected_playbook = _find_selected_playbook(selected_playbook_id, selected_playbook_type)
    messages = _build_chat_messages(
        user_message,
        fault_doc_context=build_fault_doc_context_from_playbook(selected_playbook),
    )
    messages = _append_history_messages(messages, state.get("conversation_history"))
    confirmation_response = normalize_message_content(state.get("confirmation_response", ""))
    if confirmation_response:
        _, HumanMessage, _ = load_chat_message_classes()
        messages.append(HumanMessage(content="【用户补充信息】\n" + confirmation_response))
    logger.info("=== Chat 开始 | user_message: %s", user_message[:50])
    append_fault_trace(
        "chat_start",
        {
            "user_message": user_message,
            "runtime_context": state.get("runtime_context") or {},
            "tool_count": len(tool_registry.list_definitions()),
            "playbook_route": route_trace,
        },
    )
    log_stage_duration("build_messages", started_at, message_count=len(messages), has_playbook=bool(selected_playbook_id))
    return {"messages": messages}


def call_chat_model_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    messages = list(state.get("messages") or [])
    logger.info("LLM 聊天模型开始调用 | model=%s | message_count=%d", OPENAI_CHAT_MODEL, len(messages))
    append_fault_trace(
        "chat_model_input",
        {
            "model": OPENAI_CHAT_MODEL,
            "messages": _format_message_log(messages),
        },
    )
    llm = build_chat_model()
    response = invoke_chat_model(llm, messages, model=OPENAI_CHAT_MODEL)
    usage = _extract_usage_stats(response)
    logger.info("LLM 聊天模型返回 | model=%s", OPENAI_CHAT_MODEL)
    logger.info(
        "LLM Token 用量 | model=%s | prompt_tokens=%d | completion_tokens=%d | total_tokens=%d",
        OPENAI_CHAT_MODEL,
        usage["prompt_tokens"],
        usage["completion_tokens"],
        usage["total_tokens"],
    )
    append_fault_trace(
        "chat_model_output",
        {
            "model": OPENAI_CHAT_MODEL,
            "response": _format_response_log(response),
            "usage": usage,
        },
    )
    log_stage_duration(
        "call_chat_model",
        started_at,
        message_count=len(messages),
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
    )
    return {
        "response": response,
        "response_content": normalize_message_content(getattr(response, "content", "")),
        "model_loop_count": int(state.get("model_loop_count") or 0) + 1,
    }


def interpret_model_output_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    content = normalize_message_content(state.get("response_content", ""))
    visible_content = normalize_message_content(strip_think_blocks(content))
    parsed = extract_json_payload(content)
    response_mode = normalize_message_content(state.get("response_mode", "")).lower()
    append_fault_trace(
        "model_response",
        {
            "visible_content": visible_content,
            "parsed": parsed,
            "reasoning_removed": visible_content != normalize_message_content(content),
        },
    )
    messages = list(state.get("messages") or [])
    AIMessage, HumanMessage, _ = load_chat_message_classes()
    if parsed is None:
        if response_mode == "answer":
            final_message = _render_final_message(visible_content)
            if _final_message_has_required_sections(final_message):
                append_fault_trace(
                    "chat_final",
                    {
                        "type": "plain_text",
                        "message": final_message,
                        "tool_traces": state.get("tool_traces") or [],
                    },
                )
                log_stage_duration("interpret_model_output", started_at, result_kind="final", reason="plain_text_answer")
                return {"parsed_response": None, "final_message": final_message, "result_kind": "final"}
        logger.warning(
            "模型输出重试 | reason=invalid_json | response_mode=%s | content_preview=%s",
            response_mode or "-",
            visible_content[:200],
        )
        retry_notice = (
            "上一个回复不符合格式要求。"
            "请直接输出最终答案正文。"
            "不要调用工具、不要输出 JSON、不要输出 command。"
            if response_mode == "answer"
            else (
                "上一个回复不符合格式要求。"
                "请只输出一个 JSON 对象，且如果需要排查必须输出 command，"
                "不要输出步骤说明、不要输出自然语言总结。"
            )
        )
        messages.append(
            HumanMessage(
                content=retry_notice
            )
        )
        log_stage_duration("interpret_model_output", started_at, result_kind="retry", reason="invalid_json")
        return {"messages": messages, "parsed_response": None, "result_kind": "retry"}
    response_type = str(parsed.get("type") or parsed.get("mode") or "").strip().lower()
    if response_type in {"final", "answer", "summary"}:
        final_message = _extract_final_message(parsed, content)
        if not final_message:
            raise ApiError("模型未返回有效内容")
        if not _final_message_has_required_sections(final_message):
            logger.warning(
                "模型输出重试 | reason=missing_required_sections | response_mode=%s | final_preview=%s",
                response_mode or "-",
                final_message[:200],
            )
            messages.append(
                HumanMessage(
                    content=(
                        "上一个 final 回复没有输出有效正文。"
                        "请重新输出一个 JSON 对象，保持 `type` 为 `final`，"
                        "并让 `answer` 只包含最终答案正文。"
                    )
                )
            )
            log_stage_duration("interpret_model_output", started_at, result_kind="retry", reason="missing_required_sections")
            return {"messages": messages, "parsed_response": parsed, "result_kind": "retry"}
        append_fault_trace(
            "chat_final",
            {
                "type": response_type or "final",
                "message": final_message,
                "tool_traces": state.get("tool_traces") or [],
            },
        )
        log_stage_duration("interpret_model_output", started_at, result_kind="final")
        return {"parsed_response": parsed, "final_message": final_message, "result_kind": "final"}
    if response_type == "clarify":
        questions = parsed.get("questions")
        if isinstance(questions, list):
            question_text = "\n\n".join(item for item in (_format_clarify_item(item) for item in questions) if item)
        else:
            question_text = _extract_final_message(parsed, content)
        final_message = normalize_message_content(question_text)
        if not final_message:
            raise ApiError("模型未返回有效内容")
        append_fault_trace(
            "chat_clarify",
            {
                "questions": questions if isinstance(questions, list) else final_message,
                "tool_traces": state.get("tool_traces") or [],
            },
        )
        log_stage_duration("interpret_model_output", started_at, result_kind="clarify")
        return {"parsed_response": parsed, "final_message": final_message, "result_kind": "clarify"}
    commands = _normalize_command_list(parsed)
    if response_mode == "answer" and commands:
        messages.append(
            HumanMessage(
                content=(
                    "当前处于知识库问答模式。"
                    "不要调用工具，不要编造命令。"
                    "请重新输出一个 JSON 对象，并只使用 final 或 clarify。"
                    "如果用户在要代码示例、接口说明或参数解释，请直接回答文本内容。"
                )
            )
        )
        logger.warning(
            "模型输出重试 | reason=command_in_answer_mode | response_mode=%s | content_preview=%s",
            response_mode or "-",
            visible_content[:200],
        )
        messages[0] = messages[0].__class__(content=build_knowledge_answer_system_prompt())
        log_stage_duration("interpret_model_output", started_at, result_kind="retry", reason="command_in_answer_mode")
        return {"messages": messages, "parsed_response": parsed, "result_kind": "retry"}
    if not commands:
        final_message = _extract_final_message(parsed, content)
        if not final_message:
            logger.warning(
                "模型输出重试 | reason=no_command_or_final | response_mode=%s | content_preview=%s",
                response_mode or "-",
                visible_content[:200],
            )
            messages.append(
                HumanMessage(
                    content="上一个回复没有给出可执行命令。请重新输出 command / clarify / final 的 JSON 对象。"
                )
            )
            log_stage_duration("interpret_model_output", started_at, result_kind="retry", reason="no_command_or_final")
            return {"messages": messages, "parsed_response": parsed, "result_kind": "retry"}
        append_fault_trace(
            "chat_final",
            {
                "type": "fallback",
                "message": final_message,
                "tool_traces": state.get("tool_traces") or [],
            },
        )
        log_stage_duration("interpret_model_output", started_at, result_kind="final", reason="fallback")
        return {"parsed_response": parsed, "final_message": final_message, "result_kind": "final"}
    if bool(state.get("playbook_completed")):
        logger.warning(
            "模型输出重试 | reason=command_after_playbook_completed | response_mode=%s | content_preview=%s",
            response_mode or "-",
            visible_content[:200],
        )
        messages.append(
            HumanMessage(
                content=(
                    "playbook 已经执行结束。"
                    "不要继续输出 command，也不要继续调用工具。"
                    "请直接输出一个 `type=final` 的 JSON 总结，并让 `answer` 只包含最终答案正文。"
                )
            )
        )
        log_stage_duration("interpret_model_output", started_at, result_kind="retry", reason="command_after_playbook_completed")
        return {"messages": messages, "parsed_response": parsed, "result_kind": "retry"}
    messages.append(AIMessage(content=content))
    log_stage_duration("interpret_model_output", started_at, result_kind="tool_call", command_count=len(commands))
    return {"parsed_response": parsed, "pending_commands": commands, "messages": messages, "result_kind": "tool_call"}


__all__ = ["build_messages_node", "call_chat_model_node", "interpret_model_output_node"]
