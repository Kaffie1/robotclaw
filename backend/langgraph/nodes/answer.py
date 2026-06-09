from __future__ import annotations

import json
from typing import Any

from backend.langgraph.nodes.confirm import await_confirmation_node
from backend.langgraph.prompts import build_fault_chat_system_prompt, build_knowledge_answer_system_prompt
from backend.llm.models import LLMMessage
from backend.llm.parser import extract_json_object
from backend.runtime.models import EvidenceItem, RouteDecision
from backend.tools.models import build_tool_result_schema


def build_messages_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    request = state["request"]
    response_mode = str(state.get("response_mode") or short_memory.scratchpad.get("response_mode") or "").strip().lower()
    knowledge = state.get("knowledge") or short_memory.scratchpad.get("knowledge") or {}
    playbook = state.get("playbook") or short_memory.scratchpad.get("playbook") or {}

    runtime_state.current_step = "build_messages"
    messages: list[LLMMessage] = [
        LLMMessage(
            role="system",
            content=_build_system_prompt(state, response_mode=response_mode),
        )
    ]
    messages.extend(_build_history_messages(state.get("conversation_history") or []))
    messages.append(
        LLMMessage(
            role="user",
            content=_build_user_prompt(
                query=request.content,
                response_mode=response_mode,
                knowledge=knowledge,
                playbook=playbook,
            ),
        )
    )
    short_memory.scratchpad["llm_messages"] = [{"role": item.role, "content": item.content} for item in messages]
    runtime_state.trace.append(
        RouteDecision(
            stage="消息构造",
            summary="已根据当前模式组装模型上下文",
            detail=f"response_mode={response_mode or 'chat'}，history={len(state.get('conversation_history') or [])} 条",
        )
    )
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "messages": messages,
        "model_loop_count": 0,
    }


def call_chat_model_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    runtime_state.current_step = "call_model"
    response = state["get_llm_client"]().invoke(
        messages=list(state.get("messages") or []),
        metadata={"node": "call_model"},
    )
    short_memory.scratchpad["last_model_response"] = response.content
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "response_content": response.content,
        "model_loop_count": int(state.get("model_loop_count") or 0) + 1,
    }


def interpret_model_output_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    messages = list(state.get("messages") or [])
    response_mode = str(state.get("response_mode") or short_memory.scratchpad.get("response_mode") or "").strip().lower()
    content = str(state.get("response_content") or "").strip()

    runtime_state.current_step = "interpret_output"
    parsed = _try_parse_json(content)
    if parsed is None:
        if response_mode == "answer":
            return _finish_with_answer(
                runtime_state=runtime_state,
                diagnosis=diagnosis,
                short_memory=short_memory,
                answer=content,
                result_kind="final",
            )
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    "上一个回复不符合格式要求。"
                    "请只输出一个 JSON 对象；如果需要继续诊断请输出 command 或 clarify，"
                    "如果已经有结论请输出 final。"
                ),
            )
        )
        return {
            "runtime_state": runtime_state,
            "diagnosis": diagnosis,
            "short_memory": short_memory,
            "messages": messages,
            "result_kind": "retry",
        }

    response_type = str(parsed.get("type") or parsed.get("mode") or "").strip().lower()
    if response_type in {"final", "answer", "summary"}:
        answer = _extract_final_answer(parsed, fallback=content)
        return _finish_with_answer(
            runtime_state=runtime_state,
            diagnosis=diagnosis,
            short_memory=short_memory,
            answer=answer,
            result_kind="final",
        )
    if response_type == "clarify":
        answer = _extract_clarify_text(parsed, fallback=content)
        return _finish_with_answer(
            runtime_state=runtime_state,
            diagnosis=diagnosis,
            short_memory=short_memory,
            answer=answer,
            result_kind="clarify",
        )

    commands = _normalize_command_list(parsed)
    if response_mode == "answer" and commands:
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    "当前处于知识直答模式。"
                    "不要调用工具，不要输出 command。"
                    "请直接给出最终文字答案；如果用户要 Python 代码或接口示例，请直接输出示例。"
                ),
            )
        )
        if messages:
            messages[0] = LLMMessage(role="system", content=build_knowledge_answer_system_prompt())
        return {
            "runtime_state": runtime_state,
            "diagnosis": diagnosis,
            "short_memory": short_memory,
            "messages": messages,
            "result_kind": "retry",
        }
    if not commands:
        answer = _extract_final_answer(parsed, fallback=content)
        if answer:
            return _finish_with_answer(
                runtime_state=runtime_state,
                diagnosis=diagnosis,
                short_memory=short_memory,
                answer=answer,
                result_kind="final",
            )
        messages.append(
            LLMMessage(
                role="user",
                content="上一个回复没有给出 command、clarify 或 final。请按约定重新输出。",
            )
        )
        return {
            "runtime_state": runtime_state,
            "diagnosis": diagnosis,
            "short_memory": short_memory,
            "messages": messages,
            "result_kind": "retry",
        }

    messages.append(LLMMessage(role="assistant", content=content))
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "messages": messages,
        "pending_commands": commands,
        "parsed_response": parsed,
        "result_kind": "tool_call",
    }


def call_tools_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    tool_executor = state["tool_executor"]
    messages = list(state.get("messages") or [])
    pending_commands = list(state.get("pending_commands") or [])

    runtime_state.current_step = "call_tools"
    tool_feedback_lines: list[str] = []
    all_results_payload: list[dict[str, Any]] = list(short_memory.tool_results)

    for command in pending_commands:
        tool_name = str(command.get("name") or command.get("tool_name") or "").strip()
        if not tool_name:
            continue
        tool_args = command.get("arguments") if isinstance(command.get("arguments"), dict) else {}
        planned_tools = tool_executor.plan(
            [tool_name],
            state["connected"],
            session_id=runtime_state.session_id,
            task_id=runtime_state.task_id,
        )
        if not planned_tools:
            result_payload = {
                "call_id": "",
                "tool_name": tool_name,
                "success": False,
                "status": "rejected",
                "summary": f"工具 {tool_name} 不在白名单中，已忽略本次调用。",
                "facts": {"params": tool_args},
                "data": {"result_schema": build_tool_result_schema()},
                "error": "tool_not_allowed",
                "raw_output": "",
            }
            all_results_payload.append(result_payload)
            tool_feedback_lines.append(_build_tool_feedback_message(tool_name, tool_args, result_payload))
            continue

        runtime_state.planned_tools = planned_tools
        execution_results = tool_executor.execute(planned_tools, state["connected"])
        runtime_state.tool_results = execution_results
        payloads = tool_executor.to_payload(execution_results)
        all_results_payload.extend(payloads)
        for payload in payloads:
            tool_feedback_lines.append(
                _build_tool_feedback_message(
                    payload.get("tool_name", tool_name),
                    tool_args,
                    payload,
                )
            )
            diagnosis.evidence.append(
                EvidenceItem(
                    source="tool",
                    content=str(payload.get("summary", "")).strip(),
                    confidence=0.75 if payload.get("success") else 0.45,
                )
            )

    short_memory.tool_results = all_results_payload
    if tool_feedback_lines:
        messages.append(LLMMessage(role="user", content="\n\n".join(tool_feedback_lines)))
    runtime_state.trace.append(
        RouteDecision(
            stage="工具回灌",
            summary=f"已处理 {len(pending_commands)} 个工具调用请求",
            detail="；".join(line.splitlines()[0] for line in tool_feedback_lines) if tool_feedback_lines else "无工具输出",
        )
    )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "messages": messages,
        "pending_commands": [],
        "result_kind": "tool_result",
    }


def _build_system_prompt(state: dict, *, response_mode: str) -> str:
    if response_mode == "answer":
        return build_knowledge_answer_system_prompt()
    registry = getattr(state["tool_executor"], "registry", None)
    tool_items = registry.list_definitions() if registry and hasattr(registry, "list_definitions") else []
    return build_fault_chat_system_prompt(tool_items)


def _build_history_messages(history: list[dict[str, str]]) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append(LLMMessage(role=role, content=content))
    return messages


def _build_user_prompt(*, query: str, response_mode: str, knowledge: dict[str, Any], playbook: dict[str, Any]) -> str:
    parts = [f"用户问题：{query}"]
    if response_mode == "answer":
        context = str(knowledge.get("context") or "").strip()
        citations = _format_citations(knowledge.get("citations") or [])
        if context:
            parts.append(f"知识上下文：\n{context}")
        if citations:
            parts.append(f"参考引用：\n{citations}")
        parts.append("请基于以上知识直接回答用户，必要时给出最小可用代码或接口示例。")
        return "\n\n".join(parts)

    playbook_summary = str(playbook.get("summary") or "").strip()
    playbook_detail = str(playbook.get("detail") or "").strip()
    if playbook_summary:
        parts.append(f"当前匹配到的模板摘要：{playbook_summary}")
    if playbook_detail:
        parts.append(f"模板说明：{playbook_detail}")
    parts.append("如果需要继续诊断，请只输出符合协议的 JSON。")
    return "\n\n".join(parts)


def _extract_final_answer(payload: dict[str, Any], *, fallback: str) -> str:
    for candidate in (
        payload.get("answer"),
        payload.get("content"),
        payload.get("summary"),
        payload.get("message"),
        fallback,
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _extract_clarify_text(payload: dict[str, Any], *, fallback: str) -> str:
    questions = payload.get("questions")
    if isinstance(questions, list):
        lines: list[str] = []
        for item in questions:
            if isinstance(item, dict):
                question = str(item.get("question") or item.get("content") or "").strip()
                if question:
                    lines.append(question)
            else:
                text = str(item or "").strip()
                if text:
                    lines.append(text)
        if lines:
            return "\n\n".join(lines)
    return _extract_final_answer(payload, fallback=fallback)


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


def _build_tool_feedback_message(tool_name: str, tool_args: dict[str, Any], tool_result: dict[str, Any]) -> str:
    return (
        "【工具执行结果】\n"
        f"工具: {tool_name}\n"
        f"参数: {json.dumps(tool_args, ensure_ascii=False)}\n"
        f"结果: {json.dumps(tool_result, ensure_ascii=False)}"
    )


def _format_citations(citations: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename", "") or "").strip()
        chunk_id = str(item.get("chunk_id", "") or "").strip()
        if filename or chunk_id:
            lines.append(f"- {filename}#{chunk_id}")
    return "\n".join(lines)


def _try_parse_json(content: str) -> dict[str, Any] | None:
    try:
        return extract_json_object(content)
    except Exception:
        return None


def _finish_with_answer(
    *,
    runtime_state,
    diagnosis,
    short_memory,
    answer: str,
    result_kind: str,
) -> dict:
    final_answer = str(answer or "").strip()
    diagnosis.final_answer = final_answer
    runtime_state.current_step = "completed"
    runtime_state.finished = True
    short_memory.scratchpad["final_answer"] = final_answer
    runtime_state.trace.append(
        RouteDecision(
            stage="最终回答",
            summary="已生成最终用户答复",
            detail=result_kind,
        )
    )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "final_message": final_answer,
        "result_kind": result_kind,
    }
