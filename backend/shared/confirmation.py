from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from ..core.models import ApiError
from .runtime import session_store


_CONTEXT_REF_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")
_TRUE_TEXTS = {"1", "true", "yes", "y", "ok", "confirm", "是", "确认", "同意", "允许", "可以", "继续", "好"}
_FALSE_TEXTS = {"0", "false", "no", "n", "cancel", "否", "拒绝", "不同意", "不允许", "不可以", "停止"}
MAX_CHAT_HISTORY_TURNS = 3


def _get_value_by_path(payload: Any, field: str) -> tuple[bool, Any]:
    normalized_field = str(field or "").strip()
    if not normalized_field:
        return False, None
    current = payload
    if normalized_field == ".":
        return True, current
    for segment in normalized_field.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return False, None
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current


def get_session(tool_context: dict[str, Any] | None) -> dict[str, Any] | None:
    session = (tool_context or {}).get("session")
    if isinstance(session, dict):
        return session
    session_id = get_session_id(tool_context)
    return session_store.get(session_id) if session_id else None


def get_session_id(tool_context: dict[str, Any] | None) -> str:
    if not isinstance(tool_context, dict):
        return ""
    return str(tool_context.get("session_id") or "").strip()


def get_chat_state(tool_context: dict[str, Any] | None) -> dict[str, Any]:
    session = get_session(tool_context)
    if session is None:
        return {}
    chat_state = session.get("chat_state")
    if not isinstance(chat_state, dict):
        chat_state = {}
        session["chat_state"] = chat_state
    return chat_state


def _get_chat_history_path(tool_context: dict[str, Any] | None) -> Path | None:
    session = get_session(tool_context)
    if session is None:
        return None
    raw_path = str(session.get("chat_history_path") or "").strip()
    if not raw_path:
        return None
    return Path(raw_path)


def _read_chat_history_file(tool_context: dict[str, Any] | None) -> list[dict[str, str]]:
    path = _get_chat_history_path(tool_context)
    if path is None:
        return list(get_chat_state(tool_context).get("history") or [])
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw or "[]")
    except (OSError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _write_chat_history_file(tool_context: dict[str, Any] | None, history: list[dict[str, str]]) -> None:
    path = _get_chat_history_path(tool_context)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    chat_state = get_chat_state(tool_context)
    if isinstance(chat_state, dict):
        chat_state["history"] = history


def delete_chat_history_file(tool_context: dict[str, Any] | None) -> None:
    path = _get_chat_history_path(tool_context)
    if path is None:
        get_chat_state(tool_context).pop("history", None)
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return


def get_chat_history(tool_context: dict[str, Any] | None) -> list[dict[str, str]]:
    history = _read_chat_history_file(tool_context)
    normalized_history: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            normalized_history.append({"role": role, "content": content})
    return normalized_history


def list_recent_chat_history(
    tool_context: dict[str, Any] | None,
    max_turns: int = MAX_CHAT_HISTORY_TURNS,
) -> list[dict[str, str]]:
    max_messages = max(int(max_turns or 0), 0) * 2
    history = get_chat_history(tool_context)
    if max_messages <= 0:
        return []
    return history[-max_messages:]


def append_chat_history_turn(
    tool_context: dict[str, Any] | None,
    *,
    user_message: str,
    assistant_message: str,
    max_turns: int = MAX_CHAT_HISTORY_TURNS,
) -> None:
    history = get_chat_history(tool_context)
    normalized_user_message = str(user_message or "").strip()
    normalized_assistant_message = str(assistant_message or "").strip()
    if normalized_user_message:
        history.append({"role": "user", "content": normalized_user_message})
    if normalized_assistant_message:
        history.append({"role": "assistant", "content": normalized_assistant_message})
    max_messages = max(int(max_turns or 0), 0) * 2
    if max_messages > 0 and len(history) > max_messages:
        del history[:-max_messages]
    _write_chat_history_file(tool_context, history)


def clear_chat_history(tool_context: dict[str, Any] | None) -> None:
    _write_chat_history_file(tool_context, [])


def reset_chat_state(tool_context: dict[str, Any] | None) -> None:
    chat_state = get_chat_state(tool_context)
    if isinstance(chat_state, dict):
        chat_state.clear()
    clear_chat_history(tool_context)


def get_playbook_inputs(tool_context: dict[str, Any] | None) -> dict[str, Any]:
    chat_state = get_chat_state(tool_context)
    playbook_inputs = chat_state.get("playbook_inputs")
    if not isinstance(playbook_inputs, dict):
        playbook_inputs = {}
        chat_state["playbook_inputs"] = playbook_inputs
    return playbook_inputs


def store_playbook_input(tool_context: dict[str, Any] | None, key: str, value: Any) -> None:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return
    playbook_inputs = get_playbook_inputs(tool_context)
    playbook_inputs[normalized_key] = value
    if isinstance(tool_context, dict):
        tool_context[normalized_key] = value


def get_playbook_input(tool_context: dict[str, Any] | None, key: str) -> Any:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return None
    if isinstance(tool_context, dict) and normalized_key in tool_context:
        return tool_context.get(normalized_key)
    return get_playbook_inputs(tool_context).get(normalized_key)


def clear_playbook_input(tool_context: dict[str, Any] | None, key: str) -> None:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return
    get_playbook_inputs(tool_context).pop(normalized_key, None)
    if isinstance(tool_context, dict):
        tool_context.pop(normalized_key, None)


def build_confirmation_options(options: list[Any] | None) -> list[dict[str, Any]]:
    normalized_options: list[dict[str, Any]] = []
    for index, raw_option in enumerate(options or [], start=1):
        if isinstance(raw_option, dict):
            label = str(raw_option.get("display_label") or raw_option.get("label") or raw_option.get("text") or raw_option.get("value") or raw_option.get("name") or "").strip()
            value = raw_option.get("value")
            if value is None:
                value = label
        else:
            label = str(raw_option or "").strip()
            value = label
        if not label:
            continue
        normalized_options.append(
            {
                "index": index,
                "label": label,
                "display_label": f"{index}. {label}",
                "value": value,
            }
        )
    return normalized_options


def build_confirmation_payload(
    confirmation: dict[str, Any],
    *,
    options: list[Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    normalized_options = build_confirmation_options(options)
    input_spec = confirmation.get("input") if isinstance(confirmation.get("input"), dict) else {}
    effective_input = dict(input_spec)
    mode = str(confirmation.get("mode") or "").strip().lower()
    if mode == "select" and normalized_options:
        effective_input["options"] = normalized_options
    output_spec = confirmation.get("output") if isinstance(confirmation.get("output"), dict) else {}
    resolved_message = str(message or confirmation.get("message") or "").strip()
    if not resolved_message:
        resolved_message = "请确认是否继续" if mode == "approve" else "请补充必要信息"
    return {
        "type": "clarify",
        "mode": str(confirmation.get("mode") or "").strip(),
        "question": resolved_message,
        "message": resolved_message,
        "input": effective_input,
        "options": normalized_options,
        "count": len(normalized_options),
        "output": output_spec,
    }


def store_pending_confirmation(tool_context: dict[str, Any] | None, payload: dict[str, Any]) -> None:
    get_chat_state(tool_context)["pending_confirmation"] = payload


def get_pending_confirmation(tool_context: dict[str, Any] | None) -> dict[str, Any]:
    pending = get_chat_state(tool_context).get("pending_confirmation")
    return pending if isinstance(pending, dict) else {}


def clear_pending_confirmation(tool_context: dict[str, Any] | None) -> None:
    get_chat_state(tool_context).pop("pending_confirmation", None)


def resolve_pending_confirmation_reply(
    text: str,
    tool_context: dict[str, Any] | None,
) -> dict[str, Any]:
    pending = get_pending_confirmation(tool_context)
    if not pending:
        return {"matched": False, "resolved": False}
    return {
        "matched": True,
        "resolved": False,
        "message": str(pending.get("message") or "").strip(),
        "clarify": build_confirmation_payload(
            pending.get("confirmation") if isinstance(pending.get("confirmation"), dict) else {},
            options=pending.get("options") if isinstance(pending.get("options"), list) else [],
            message=pending.get("message"),
        ),
    }


def get_context_value(tool_context: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(tool_context, dict):
        return None
    return tool_context.get(str(key or "").strip())


def expand_context_references(value: Any, tool_context: dict[str, Any] | None) -> Any:
    if isinstance(value, dict):
        if "from_context" in value and len(value) == 1:
            return get_context_value(tool_context, str(value.get("from_context") or ""))
        return {key: expand_context_references(item, tool_context) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_context_references(item, tool_context) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(_CONTEXT_REF_PATTERN.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return get_context_value(tool_context, matches[0].group(1))

    def replace_match(match: re.Match[str]) -> str:
        resolved = get_context_value(tool_context, match.group(1))
        return "" if resolved is None else str(resolved)

    return _CONTEXT_REF_PATTERN.sub(replace_match, value)


def has_context_value(tool_context: dict[str, Any] | None, key: str) -> bool:
    value = get_context_value(tool_context, key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def get_confirmation_request(
    node_spec: dict[str, Any],
    tool_context: dict[str, Any] | None,
    *,
    playbook_id: str,
    playbook_title: str,
    node_path: str,
    stage: str = "before",
    step_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """根据节点的确认配置和当前阶段构建一个确认请求，如果当前阶段不需要确认则返回 None"""
    if not bool(node_spec.get("require_confirmation")):
        return None
    confirmation = node_spec.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ApiError(f"确认节点缺少 confirmation 配置: {playbook_id}.{node_path}")
    when = str(confirmation.get("when") or "before").strip().lower()
    normalized_stage = str(stage or "before").strip().lower()
    if when not in {"before", "after"}:
        raise ApiError(f"当前仅支持 before/after 确认: {playbook_id}.{node_path}")
    if when != normalized_stage:
        return None
    mode = str(confirmation.get("mode") or "input").strip().lower()
    output = confirmation.get("output") if isinstance(confirmation.get("output"), dict) else {}
    store_as = str(output.get("store_as") or "").strip()
    if store_as and has_context_value(tool_context, store_as):
        return None
    raw_message = str(
        confirmation.get("message")
        or node_spec.get("failure_message")
        or f"请确认步骤 {node_spec.get('name') or node_spec.get('tool_name') or node_path} 所需信息"
    ).strip()
    if not raw_message:
        raise ApiError(f"确认节点缺少提示语: {playbook_id}.{node_path}")
    input_spec = confirmation.get("input") if isinstance(confirmation.get("input"), dict) else {}
    request_input = dict(input_spec)
    if mode == "select":
        request_input["options"] = _resolve_confirmation_options(
            input_spec,
            step_result=step_result,
        )
    effective_confirmation = dict(confirmation)
    effective_confirmation["input"] = request_input
    message = _build_confirmation_message(raw_message, mode, effective_confirmation)
    return {
        "type": "playbook_confirmation",
        "playbook_id": playbook_id,
        "playbook_title": playbook_title,
        "node_path": node_path,
        "node_name": str(node_spec.get("name") or node_spec.get("tool_name") or "").strip(),
        "tool_name": str(node_spec.get("tool_name") or "").strip(),
        "message": message,
        "mode": mode,
        "confirmation": confirmation,
        "input": request_input,
        "output": output,
    }


def _resolve_confirmation_options(
    input_spec: dict[str, Any],
    *,
    step_result: dict[str, Any] | None = None,
) -> list[Any]:
    direct_options = input_spec.get("options")
    if isinstance(direct_options, list) and direct_options:
        return direct_options

    options_source = input_spec.get("options_source") if isinstance(input_spec.get("options_source"), dict) else {}
    if not options_source:
        return []
    source_field = str(options_source.get("field") or "raw_result").strip() or "raw_result"
    source_parser = str(options_source.get("parser") or "").strip().lower()
    list_key = str(options_source.get("list_key") or "").strip()
    payload = step_result if isinstance(step_result, dict) else {}
    found, value = _get_value_by_path(payload, source_field)
    if not found:
        return []
    if list_key:
        found, nested_value = _get_value_by_path(value, list_key)
        if found:
            value = nested_value
    if source_parser == "string_list":
        return _parse_string_list_options(value)
    if isinstance(value, list):
        return value
    return []


def _parse_string_list_options(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in re.split(r"[\r\n,]+", text) if item.strip()]
    return []


def _build_confirmation_message(base_message: str, mode: str, confirmation: dict[str, Any]) -> str:
    normalized_base = base_message.strip()
    if mode == "approve":
        return f"{normalized_base}\n可直接回复：允许 / 拒绝"
    if mode == "input":
        input_spec = confirmation.get("input") if isinstance(confirmation.get("input"), dict) else {}
        label = str(input_spec.get("label") or "").strip()
        placeholder = str(input_spec.get("placeholder") or "").strip()
        parts = [normalized_base]
        if label:
            parts.append(f"请输入：{label}")
        if placeholder:
            parts.append(f"示例：{placeholder}")
        return "\n".join(parts)
    if mode == "select":
        input_spec = confirmation.get("input") if isinstance(confirmation.get("input"), dict) else {}
        options = _normalize_select_options(input_spec.get("options"))
        if not options:
            return normalized_base
        option_lines = [f"{option['index'] + 1}. {option['label']}" for option in options]
        return "\n".join([normalized_base, "可回复序号或选项文本：", *option_lines])
    return normalized_base


def _coerce_boolean(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized in _TRUE_TEXTS:
        return True
    if normalized in _FALSE_TEXTS:
        return False
    raise ApiError("无法识别你的确认结果。请直接回复：允许 / 拒绝")


def _normalize_select_options(raw_options: Any) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    if not isinstance(raw_options, list):
        return options
    for index, item in enumerate(raw_options):
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or item.get("value") or "").strip()
            value = item.get("value", label)
        else:
            label = str(item or "").strip()
            value = label
        if not label:
            continue
        options.append({"label": label, "value": value, "index": index})
    return options


def resolve_confirmation_value(request: dict[str, Any], response_text: str) -> Any:
    """根据确认请求的配置解析用户的回复文本，支持不同的确认模式和输入类型"""
    mode = str(request.get("mode") or "input").strip().lower()
    input_spec = request.get("input") if isinstance(request.get("input"), dict) else {}
    output_spec = request.get("output") if isinstance(request.get("output"), dict) else {}
    response = str(response_text or "").strip()

    if mode == "approve":
        approved = _coerce_boolean(response)
        output_type = str(output_spec.get("type") or "boolean").strip().lower()
        if output_type in {"", "boolean", "raw_input"}:
            return approved
        raise ApiError(f"暂不支持的 approve 输出类型: {output_type}")

    if mode == "input":
        allow_empty = bool(input_spec.get("allow_empty"))
        if not response and not allow_empty:
            raise ApiError("确认输入不能为空")
        input_type = str(input_spec.get("type") or "text").strip().lower()
        if input_type in {"text", "string"}:
            value: Any = response
        elif input_type == "number":
            try:
                value = float(response)
            except ValueError as exc:
                raise ApiError("请输入数字") from exc
        elif input_type == "integer":
            try:
                value = int(response)
            except ValueError as exc:
                raise ApiError("请输入整数") from exc
        elif input_type == "boolean":
            value = _coerce_boolean(response)
        elif input_type == "index":
            try:
                value = int(response)
            except ValueError as exc:
                raise ApiError("请输入索引数字") from exc
        else:
            raise ApiError(f"暂不支持的确认输入类型: {input_type}")
        return value

    if mode == "select":
        options = _normalize_select_options(input_spec.get("options"))
        if not options:
            raise ApiError("select 确认缺少 options")
        if not response and bool(input_spec.get("auto_select_if_single")) and len(options) == 1:
            selected = options[0]
        else:
            selected = None
            if response.isdigit():
                selected_index = int(response)
                for option in options:
                    if option["index"] == selected_index or option["index"] + 1 == selected_index:
                        selected = option
                        break
            if selected is None:
                for option in options:
                    if response in {str(option["label"]).strip(), str(option["value"]).strip()}:
                        selected = option
                        break
            if selected is None:
                raise ApiError("未匹配到可选项，请按编号或选项文本回复")
        output_type = str(output_spec.get("type") or "selected_option_value").strip().lower()
        if output_type == "selected_option_value":
            return selected["value"]
        if output_type == "selected_option_label":
            return selected["label"]
        if output_type == "selected_option_index":
            return selected["index"]
        raise ApiError(f"暂不支持的 select 输出类型: {output_type}")

    raise ApiError(f"暂不支持的确认模式: {mode}")


def apply_confirmation_response(
    tool_context: dict[str, Any] | None,
    request: dict[str, Any] | None,
    response_text: str,
) -> dict[str, Any]:
    """将确认结果存储到工具上下文中，优先存储到 output.store_as 指定的字段"""
    updated = dict(tool_context or {})
    if not isinstance(request, dict):
        return updated
    output_spec = request.get("output") if isinstance(request.get("output"), dict) else {}
    store_as = str(output_spec.get("store_as") or "").strip()
    if not store_as:
        return updated
    updated[store_as] = resolve_confirmation_value(request, response_text)
    return updated
