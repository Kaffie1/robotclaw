from __future__ import annotations

from typing import Any

from ...core.models import ApiError

ALLOWED_BT_NODE_TYPES = {"sequence", "selector", "condition", "action", "call_playbook", "result"}
ALLOWED_WORKFLOW_TYPES = {"fault", "normal"}


def _normalize_context_schema(playbook: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_schema = playbook.get("context_schema")
    if not isinstance(raw_schema, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in raw_schema.items():
        normalized_key = str(key or "").strip()
        if normalized_key and isinstance(value, dict):
            normalized[normalized_key] = value
    return normalized


def _validate_context_schema(playbook: dict[str, Any], *, playbook_id: str) -> dict[str, dict[str, Any]]:
    schema = _normalize_context_schema(playbook)
    for key, spec in schema.items():
        source = str(spec.get("source") or "runtime").strip().lower()
        if source not in {"input", "runtime", "confirmation"}:
            raise ApiError(f"context_schema.source 不支持: {playbook_id}.{key}")
    return schema


def _validate_context_key_exists(context_schema: dict[str, dict[str, Any]], key: str, *, playbook_id: str, path: str, field_name: str) -> None:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ApiError(f"{field_name} 不能为空: {playbook_id}.{path}")
    if context_schema and normalized_key not in context_schema:
        raise ApiError(f"{field_name} 未在 context_schema 中声明: {playbook_id}.{path}.{normalized_key}")


def _validate_context_references(value: Any, context_schema: dict[str, dict[str, Any]], *, playbook_id: str, path: str) -> None:
    if isinstance(value, dict):
        if "from_context" in value and len(value) == 1:
            _validate_context_key_exists(
                context_schema,
                str(value.get("from_context") or "").strip(),
                playbook_id=playbook_id,
                path=path,
                field_name="from_context",
            )
            return
        for key, item in value.items():
            _validate_context_references(item, context_schema, playbook_id=playbook_id, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_context_references(item, context_schema, playbook_id=playbook_id, path=f"{path}[{index}]")


def _validate_confirmation_spec(node: dict[str, Any], *, playbook_id: str, path: str) -> None:
    _validate_confirmation_spec_with_context(node, playbook_id=playbook_id, path=path, context_schema={})


def _validate_confirmation_spec_with_context(
    node: dict[str, Any],
    *,
    playbook_id: str,
    path: str,
    context_schema: dict[str, dict[str, Any]],
) -> None:
    if not bool(node.get("require_confirmation")) and "confirmation" not in node:
        return
    confirmation = node.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ApiError(f"确认节点缺少 confirmation 配置: {playbook_id}.{path}")
    when = str(confirmation.get("when") or "before").strip().lower()
    if when not in {"before", "after"}:
        raise ApiError(f"confirmation.when 不支持: {playbook_id}.{path}")
    mode = str(confirmation.get("mode") or "input").strip().lower()
    if mode not in {"approve", "input", "select"}:
        raise ApiError(f"confirmation.mode 不支持: {playbook_id}.{path}")
    if not str(confirmation.get("message") or "").strip():
        raise ApiError(f"confirmation.message 不能为空: {playbook_id}.{path}")
    output = confirmation.get("output")
    if not isinstance(output, dict):
        raise ApiError(f"confirmation.output 必须是对象: {playbook_id}.{path}")
    store_as = str(output.get("store_as") or "").strip()
    _validate_context_key_exists(context_schema, store_as, playbook_id=playbook_id, path=path, field_name="confirmation.output.store_as")
    if mode in {"input", "select"}:
        input_spec = confirmation.get("input")
        if not isinstance(input_spec, dict):
            raise ApiError(f"confirmation.input 必须是对象: {playbook_id}.{path}")
    if mode == "select":
        options = confirmation.get("input", {}).get("options") if isinstance(confirmation.get("input"), dict) else None
        if options is not None and not isinstance(options, list):
            raise ApiError(f"confirmation.input.options 必须是列表: {playbook_id}.{path}")
        options_source = confirmation.get("input", {}).get("options_source") if isinstance(confirmation.get("input"), dict) else None
        if options_source is not None and not isinstance(options_source, dict):
            raise ApiError(f"confirmation.input.options_source 必须是对象: {playbook_id}.{path}")
        if isinstance(options_source, dict) and "from_context" in options_source:
            _validate_context_key_exists(
                context_schema,
                str(options_source.get("from_context") or "").strip(),
                playbook_id=playbook_id,
                path=path,
                field_name="confirmation.input.options_source.from_context",
            )


def validate_playbook_spec(playbook: dict[str, Any]) -> None:
    if not isinstance(playbook, dict):
        raise ApiError("playbook 格式错误")
    playbook_id = str(playbook.get("id") or "").strip()
    if not playbook_id:
        raise ApiError("playbook 缺少 id")
    workflow_type = str(playbook.get("type") or playbook.get("workflow_type") or "").strip().lower()
    if workflow_type not in ALLOWED_WORKFLOW_TYPES:
        raise ApiError(f"playbook.type 不支持: {playbook_id}")
    context_schema = _validate_context_schema(playbook, playbook_id=playbook_id)

    root = playbook.get("root")
    if not isinstance(root, dict):
        raise ApiError(f"playbook 缺少行为树 root: {playbook_id}")
    validate_bt_node_spec(root, playbook_id=playbook_id, path="root", context_schema=context_schema)

    for list_field in ("escalation_notes", "execution_notes", "global_rules"):
        if list_field in playbook and not isinstance(playbook.get(list_field), list):
            raise ApiError(f"{list_field} 必须是列表: {playbook_id}")


def validate_bt_node_spec(
    node: Any,
    *,
    playbook_id: str,
    path: str,
    context_schema: dict[str, dict[str, Any]] | None = None,
) -> None:
    normalized_context_schema = context_schema or {}
    if not isinstance(node, dict):
        raise ApiError(f"行为树节点必须是对象: {playbook_id}.{path}")
    node_type = str(node.get("type") or "").strip().lower()
    if not node_type:
        raise ApiError(f"行为树节点缺少 type: {playbook_id}.{path}")
    if node_type not in ALLOWED_BT_NODE_TYPES:
        raise ApiError(f"行为树节点类型不支持: {node_type}")
    if node_type in {"sequence", "selector"}:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            raise ApiError(f"组合节点缺少 children: {playbook_id}.{path}")
        for index, child in enumerate(children):
            validate_bt_node_spec(
                child,
                playbook_id=playbook_id,
                path=f"{path}.children[{index}]",
                context_schema=normalized_context_schema,
            )
        return
    if node_type in {"condition", "action"}:
        tool_name = str(node.get("tool_name") or "").strip()
        if not tool_name:
            raise ApiError(f"行为树叶子节点缺少 tool_name: {playbook_id}.{path}")
        arguments = node.get("arguments")
        if arguments is not None and not isinstance(arguments, dict):
            raise ApiError(f"行为树叶子节点 arguments 必须是对象: {playbook_id}.{path}")
        _validate_context_references(arguments or {}, normalized_context_schema, playbook_id=playbook_id, path=f"{path}.arguments")
        result_mapping = node.get("result_mapping")
        if result_mapping is not None and not isinstance(result_mapping, dict):
            raise ApiError(f"行为树叶子节点 result_mapping 必须是对象: {playbook_id}.{path}")
        if isinstance(result_mapping, dict):
            for _, target_key in result_mapping.items():
                _validate_context_key_exists(
                    normalized_context_schema,
                    str(target_key or "").strip(),
                    playbook_id=playbook_id,
                    path=path,
                    field_name="result_mapping",
                )
        _validate_confirmation_spec_with_context(
            node,
            playbook_id=playbook_id,
            path=path,
            context_schema=normalized_context_schema,
        )
        return
    if node_type == "call_playbook":
        failure_playbook_id = str(node.get("playbook_id") or node.get("target_playbook_id") or "").strip()
        if not failure_playbook_id:
            raise ApiError(f"行为树 call_playbook 节点缺少 playbook_id: {playbook_id}.{path}")
        return
    if node_type == "result":
        status = str(node.get("status") or "").strip().lower()
        if status not in {"success", "failure", "running"}:
            raise ApiError(f"行为树 result 节点缺少有效 status: {playbook_id}.{path}")
