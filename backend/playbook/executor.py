from __future__ import annotations

from dataclasses import asdict
import json
import re
import time
from typing import Any

from backend.playbook.loader import find_playbook_by_id
from backend.playbook.models import BTNodeSpec, BlackboardSnapshot, NodeExecutionResult, PlaybookSpec
from backend.rule.models import RuleCall
from backend.shared import get_logger
from backend.tools.models import ToolResult, build_tool_call, build_tool_result, get_tool_result_output


logger = get_logger("playbook.executor")


def _format_log_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def execute_playbook(
    spec: PlaybookSpec,
    *,
    tool_executor,
    rule_engine,
    connected: bool,
    context: dict[str, Any],
    resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    logger.info(
        "Playbook execution started playbook_id=%s playbook_title=%s connected=%s resume=%s",
        spec.meta.playbook_id,
        spec.meta.name,
        connected,
        bool(resume),
    )
    blackboard = {
        "context": dict(context),
        "variables": {},
        "observations": {},
        "tool_outputs": {},
        "rule_results": [],
        "active_playbooks": [spec.meta.playbook_id],
        "resume": dict(resume or {}),
        "current_node_id": spec.root.node_id,
    }
    steps: list[dict[str, Any]] = []
    completed_nodes: list[str] = []
    failed_nodes: list[str] = []
    result = _execute_node(
        spec.root,
        spec=spec,
        tool_executor=tool_executor,
        rule_engine=rule_engine,
        connected=connected,
        blackboard=blackboard,
        steps=steps,
        completed_nodes=completed_nodes,
        failed_nodes=failed_nodes,
    )
    passed = bool(result.get("passed", False))
    conclusion = str(result.get("message") or "").strip()
    next_action = ""
    if not passed:
        next_action = str(result.get("failure_message") or "").strip() or "当前 playbook 未通过，请继续人工排查。"
    payload = {
        "playbook_id": spec.meta.playbook_id,
        "playbook_title": spec.meta.name,
        "executed": True,
        "passed": passed,
        "steps": steps,
        "conclusion": conclusion or ("playbook 执行完成" if passed else "playbook 执行未通过"),
        "next_action": next_action,
        "current_node_id": str(result.get("node_id") or spec.root.node_id),
        "completed_nodes": completed_nodes,
        "failed_nodes": failed_nodes,
        "playbook_context": dict(blackboard["context"]),
        "blackboard_snapshot": asdict(_snapshot_blackboard(blackboard)),
        "rule_results": list(blackboard["rule_results"]),
        "pending_confirmation": result.get("pending_confirmation"),
    }
    logger.info(
        "Playbook execution finished playbook_id=%s passed=%s current_node_id=%s next_action=%s pending_confirmation=%s",
        spec.meta.playbook_id,
        passed,
        payload["current_node_id"],
        payload["next_action"],
        bool(payload["pending_confirmation"]),
    )
    return payload


def _execute_node(
    node: BTNodeSpec,
    *,
    spec: PlaybookSpec,
    tool_executor,
    rule_engine,
    connected: bool,
    blackboard: dict[str, Any],
    steps: list[dict[str, Any]],
    completed_nodes: list[str],
    failed_nodes: list[str],
) -> dict[str, Any]:
    blackboard["current_node_id"] = node.node_id
    if node.node_type == "sequence":
        return _execute_sequence(node, spec=spec, tool_executor=tool_executor, rule_engine=rule_engine, connected=connected, blackboard=blackboard, steps=steps, completed_nodes=completed_nodes, failed_nodes=failed_nodes)
    if node.node_type == "selector":
        return _execute_selector(node, spec=spec, tool_executor=tool_executor, rule_engine=rule_engine, connected=connected, blackboard=blackboard, steps=steps, completed_nodes=completed_nodes, failed_nodes=failed_nodes)
    if node.node_type == "call_playbook":
        return _execute_call_playbook(
            node,
            spec=spec,
            tool_executor=tool_executor,
            rule_engine=rule_engine,
            connected=connected,
            blackboard=blackboard,
            steps=steps,
            completed_nodes=completed_nodes,
            failed_nodes=failed_nodes,
        )
    if node.node_type == "input":
        return _execute_input_node(node, blackboard=blackboard, steps=steps, completed_nodes=completed_nodes)
    if node.node_type == "result":
        return _execute_result_node(node, steps=steps, completed_nodes=completed_nodes, failed_nodes=failed_nodes)
    return _execute_leaf(node, tool_executor=tool_executor, rule_engine=rule_engine, connected=connected, blackboard=blackboard, steps=steps, completed_nodes=completed_nodes, failed_nodes=failed_nodes)


def _execute_call_playbook(
    node: BTNodeSpec,
    *,
    spec: PlaybookSpec,
    tool_executor,
    rule_engine,
    connected: bool,
    blackboard: dict[str, Any],
    steps: list[dict[str, Any]],
    completed_nodes: list[str],
    failed_nodes: list[str],
) -> dict[str, Any]:
    target_playbook_id = _node_target_playbook_id(node).strip()
    active_playbooks = blackboard.setdefault("active_playbooks", [])
    if target_playbook_id in active_playbooks:
        message = f"检测到循环调用 playbook：{target_playbook_id}"
        steps.append(
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "name": node.name,
                "target_playbook_id": target_playbook_id,
                "passed": False,
                "output": message,
            }
        )
        failed_nodes.append(node.node_id)
        return {"passed": False, "node_id": node.node_id, "message": message, "failure_message": node.failure_message or message}

    child_spec = find_playbook_by_id(target_playbook_id)
    if child_spec is None:
        message = f"未找到子 playbook：{target_playbook_id}"
        steps.append(
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "name": node.name,
                "target_playbook_id": target_playbook_id,
                "passed": False,
                "output": message,
            }
        )
        failed_nodes.append(node.node_id)
        return {"passed": False, "node_id": node.node_id, "message": message, "failure_message": node.failure_message or message}

    active_playbooks.append(target_playbook_id)
    try:
        child_result = _execute_node(
            child_spec.root,
            spec=child_spec,
            tool_executor=tool_executor,
            rule_engine=rule_engine,
            connected=connected,
            blackboard=blackboard,
            steps=steps,
            completed_nodes=completed_nodes,
            failed_nodes=failed_nodes,
        )
    finally:
        active_playbooks.pop()

    step = {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "name": node.name,
        "target_playbook_id": target_playbook_id,
        "passed": bool(child_result.get("passed", False)),
        "output": str(child_result.get("message") or node.success_message or node.failure_message or node.name).strip(),
    }
    steps.append(step)
    if step["passed"]:
        completed_nodes.append(node.node_id)
    else:
        failed_nodes.append(node.node_id)
    return {
        "passed": step["passed"],
        "node_id": child_result.get("node_id") or node.node_id,
        "message": step["output"],
        "failure_message": node.failure_message or child_result.get("failure_message"),
        "pending_confirmation": child_result.get("pending_confirmation"),
    }


def _execute_sequence(node: BTNodeSpec, **kwargs) -> dict[str, Any]:
    last_success_message = node.success_message or f"{node.name} 执行完成"
    for child in node.children:
        if _should_skip_for_resume(child, kwargs["blackboard"]):
            continue
        result = _execute_node(child, **kwargs)
        if result.get("pending_confirmation"):
            return result
        if not result.get("passed", False):
            return {
                "passed": False,
                "node_id": result.get("node_id") or child.node_id,
                "message": result.get("message") or node.failure_message or child.failure_message or f"{child.name} 执行失败",
                "failure_message": result.get("failure_message") or node.failure_message or child.failure_message,
            }
        last_success_message = str(result.get("message") or last_success_message)
    return {"passed": True, "node_id": node.node_id, "message": last_success_message}


def _execute_selector(node: BTNodeSpec, **kwargs) -> dict[str, Any]:
    last_failure_message = node.failure_message or f"{node.name} 所有分支均未通过"
    for child in node.children:
        if _should_skip_for_resume(child, kwargs["blackboard"]):
            continue
        result = _execute_node(child, **kwargs)
        if result.get("pending_confirmation"):
            return result
        if result.get("passed", False):
            return {"passed": True, "node_id": result.get("node_id") or child.node_id, "message": result.get("message") or node.success_message or child.success_message or f"{child.name} 分支通过"}
        last_failure_message = str(result.get("message") or last_failure_message)
    return {"passed": False, "node_id": node.node_id, "message": last_failure_message, "failure_message": last_failure_message}


def _execute_leaf(
    node: BTNodeSpec,
    *,
    tool_executor,
    rule_engine,
    connected: bool,
    blackboard: dict[str, Any],
    steps: list[dict[str, Any]],
    completed_nodes: list[str],
    failed_nodes: list[str],
) -> dict[str, Any]:
    resume_entry = _get_resume_for_node(blackboard, node)

    if _node_requires_confirmation(node) and str((_node_confirmation(node) or {}).get("when") or "before").strip().lower() == "before" and resume_entry is None:
        return {
            "passed": False,
            "node_id": node.node_id,
            "pending_confirmation": _build_confirmation(node, blackboard=blackboard),
            "message": str((_node_confirmation(node) or {}).get("message") or node.name).strip(),
        }
    if resume_entry is not None:
        _apply_confirmation_output(node, blackboard=blackboard, resume_entry=resume_entry)

    attempts = max(1, _node_confirm_times(node))
    tool_result = None
    passed = True
    rule_result = None
    for attempt_index in range(attempts):
        if tool_result is None and node.tool and _node_before_wait_seconds(node) > 0:
            time.sleep(_node_before_wait_seconds(node))
        tool_result = _load_resume_tool_result(resume_entry) if resume_entry is not None and attempt_index == 0 else None
        executed_tool_this_attempt = False
        if tool_result is None and node.tool:
            tool_result = _execute_tool(node, tool_executor=tool_executor, connected=connected, blackboard=blackboard)
            executed_tool_this_attempt = True
        if executed_tool_this_attempt and _node_after_wait_seconds(node) > 0:
            time.sleep(_node_after_wait_seconds(node))
        if node.rule is None:
            if node.node_type == "condition" and isinstance(tool_result, dict) and node.tool:
                passed = bool(tool_result.get("success", True))
            else:
                passed = True
            rule_result = None
        else:
            rule_call_inputs = _build_rule_inputs(node, tool_result=tool_result, blackboard=blackboard)
            rule_result = rule_engine.evaluate(RuleCall(rule_id=node.rule.rule_id, inputs=rule_call_inputs))
            blackboard["rule_results"].append(asdict(rule_result))
            passed = rule_result.passed == node.rule.expected
        if passed or attempt_index >= attempts - 1:
            break

    if _node_requires_confirmation(node) and str((_node_confirmation(node) or {}).get("when") or "").strip().lower() == "after" and resume_entry is None:
        pending = _build_confirmation(node, blackboard=blackboard, tool_result=tool_result)
        return {
            "passed": False,
            "node_id": node.node_id,
            "pending_confirmation": pending,
            "message": str((_node_confirmation(node) or {}).get("message") or node.name).strip(),
        }

    step = {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "name": node.name,
        "tool_name": node.tool,
        "arguments": dict(node.args),
        "passed": passed,
        "output": (
            str(tool_result.get("summary", "")).strip() if isinstance(tool_result, dict) else ""
        ) or (node.success_message if passed else node.failure_message),
        "rule_result": asdict(rule_result) if rule_result is not None else None,
    }
    _log_leaf_execution(node=node, step=step, tool_result=tool_result, rule_result=rule_result)
    steps.append(step)
    if passed:
        completed_nodes.append(node.node_id)
    else:
        failed_nodes.append(node.node_id)
    _record_observation(node, blackboard=blackboard, passed=passed, tool_result=tool_result, rule_result=rule_result)
    execution_result = NodeExecutionResult(
        node_id=node.node_id,
        status="success" if passed else "failure",
        output={"summary": step["output"]},
        rule_result=asdict(rule_result) if rule_result is not None else None,
        message=step["output"] or node.name,
    )
    return {
        "passed": passed,
        "node_id": node.node_id,
        "message": execution_result.message or (node.success_message if passed else node.failure_message) or node.name,
        "failure_message": node.failure_message,
    }


def _execute_tool(node: BTNodeSpec, *, tool_executor, connected: bool, blackboard: dict[str, Any]) -> ToolResult:
    call = build_tool_call(node.tool, params=_resolve_arguments(node.args, blackboard))
    result = tool_executor.execute([call], connected)[0]
    blackboard["tool_outputs"][node.node_id] = dict(result)
    blackboard["variables"][node.node_id] = dict(result)
    log_payload = {
        "event": "playbook_tool_result",
        "node_id": node.node_id,
        "tool_name": node.tool,
        "success": result.get("success"),
        "status": result.get("status"),
        "summary": str(result.get("summary") or "").strip(),
        "error": str(result.get("error") or "").strip(),
        "exit_code": get_tool_result_output(result).get("exit_code"),
        "result": result,
    }
    logger.info(
        "Playbook tool result\n%s",
        _format_log_payload(log_payload),
    )
    return result


def _log_leaf_execution(
    *,
    node: BTNodeSpec,
    step: dict[str, Any],
    tool_result: ToolResult | None,
    rule_result: Any,
) -> None:
    log_payload = {
        "event": "playbook_node_evaluated",
        "node_id": node.node_id,
        "tool_name": node.tool,
        "input": _build_log_execution_input(step=step, tool_result=tool_result),
        "output": str(step["output"] or "").strip(),
        "passed": step["passed"],
    }
    logger.info(
        "Playbook node evaluated\n%s",
        _format_log_payload(log_payload),
    )
    if not step["passed"]:
        failure_payload = {
            "event": "playbook_node_failed",
            "node_id": node.node_id,
            "tool_name": node.tool,
            "exit_code": get_tool_result_output(tool_result).get("exit_code") if isinstance(tool_result, dict) else None,
            "summary": str(step["output"] or "").strip(),
            "error": str((tool_result or {}).get("error") or "").strip() if isinstance(tool_result, dict) else "",
            "rule_failures": _summarize_rule_failures(rule_result),
        }
        logger.warning(
            "Playbook node failed\n%s",
            _format_log_payload(failure_payload),
        )


def _build_log_execution_input(*, step: dict[str, Any], tool_result: ToolResult | None) -> dict[str, Any]:
    if isinstance(tool_result, dict):
        data = tool_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("params"), dict):
            return dict(data.get("params") or {})
    return dict(step.get("arguments") or {})


def _summarize_rule_failures(rule_result: Any) -> str:
    if rule_result is None:
        return ""
    detail = getattr(rule_result, "detail", None)
    if not isinstance(detail, dict):
        return ""
    conditions = detail.get("conditions")
    if not isinstance(conditions, list):
        return ""
    failed_items: list[str] = []
    for item in conditions:
        if not isinstance(item, dict) or bool(item.get("passed", False)):
            continue
        field = str(item.get("field") or "").strip()
        op = str(item.get("op") or "").strip()
        actual = json.dumps(item.get("actual"), ensure_ascii=False)
        expected = json.dumps(item.get("expected"), ensure_ascii=False)
        reason = str(item.get("reason") or "").strip()
        if reason:
            failed_items.append(f"{field} {reason}")
        else:
            failed_items.append(f"{field} {op} actual={actual} expected={expected}")
    return "；".join(failed_items)


def _execute_input_node(
    node: BTNodeSpec,
    *,
    blackboard: dict[str, Any],
    steps: list[dict[str, Any]],
    completed_nodes: list[str],
) -> dict[str, Any]:
    resume_entry = _get_resume_for_node(blackboard, node)
    if resume_entry is None:
        prompt = node.prompt or str((_node_confirmation(node) or {}).get("message") or node.name).strip()
        return {
            "passed": False,
            "node_id": node.node_id,
            "pending_confirmation": _build_input_request(node, prompt),
            "message": prompt,
        }

    value = _resolve_resume_value(node=node, resume_entry=resume_entry)
    store_as = str(((_node_confirmation(node) or {}).get("output") or {}).get("store_as") or node.node_id).strip() or node.node_id
    blackboard["context"][store_as] = value
    step = {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "name": node.name,
        "passed": True,
        "output": f"{store_as} 已写入上下文",
    }
    steps.append(step)
    completed_nodes.append(node.node_id)
    return {"passed": True, "node_id": node.node_id, "message": step["output"]}


def _execute_result_node(
    node: BTNodeSpec,
    *,
    steps: list[dict[str, Any]],
    completed_nodes: list[str],
    failed_nodes: list[str],
) -> dict[str, Any]:
    status = str(node.args.get("status") or "success").strip().lower()
    message = str(node.args.get("message") or node.success_message or node.failure_message or node.name).strip()
    passed = status != "failure"
    step = {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "name": node.name,
        "passed": passed,
        "output": message,
    }
    steps.append(step)
    if passed:
        completed_nodes.append(node.node_id)
    else:
        failed_nodes.append(node.node_id)
    return {"passed": passed, "node_id": node.node_id, "message": message, "failure_message": node.failure_message or message}


def _node_requires_confirmation(node: BTNodeSpec) -> bool:
    return bool(getattr(node, "require_confirmation", False))


def _node_confirmation(node: BTNodeSpec) -> dict[str, Any]:
    raw = getattr(node, "confirmation", {})
    return dict(raw) if isinstance(raw, dict) else {}


def _node_wait_seconds(node: BTNodeSpec) -> int:
    return int(getattr(node, "wait_seconds", 0) or 0)


def _node_before_wait_seconds(node: BTNodeSpec) -> int:
    return int(getattr(node, "before_wait_seconds", 0) or 0)


def _node_after_wait_seconds(node: BTNodeSpec) -> int:
    configured = getattr(node, "after_wait_seconds", None)
    if configured is not None:
        return int(configured or 0)
    return _node_wait_seconds(node)


def _node_confirm_times(node: BTNodeSpec) -> int:
    return max(1, int(getattr(node, "confirm_times", 1) or 1))


def _node_target_playbook_id(node: BTNodeSpec) -> str:
    return str(getattr(node, "target_playbook_id", "") or "").strip()


def _resolve_arguments(arguments: dict[str, Any], blackboard: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, dict) and "from_context" in value:
            resolved[key] = blackboard["context"].get(str(value.get("from_context") or "").strip())
        elif isinstance(value, dict):
            resolved[key] = _resolve_arguments(value, blackboard)
        elif isinstance(value, list):
            resolved[key] = [_resolve_argument_item(item, blackboard) for item in value]
        else:
            resolved[key] = _resolve_argument_item(value, blackboard)
    return resolved


def _resolve_argument_item(value: Any, blackboard: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    template_matches = re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", value)
    if not template_matches:
        return value
    if value.strip().startswith("{{") and value.strip().endswith("}}") and len(template_matches) == 1:
        return _resolve_runtime_value(template_matches[0], blackboard)
    resolved_text = value
    for expression in template_matches:
        replacement = _resolve_runtime_value(expression, blackboard)
        resolved_text = resolved_text.replace(f"{{{{ {expression} }}}}", str(replacement if replacement is not None else ""))
        resolved_text = resolved_text.replace(f"{{{{{expression}}}}}", str(replacement if replacement is not None else ""))
    return resolved_text


def _build_rule_inputs(node: BTNodeSpec, *, tool_result: ToolResult | None, blackboard: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "context": dict(blackboard["context"]),
        "tool_outputs": dict(blackboard["tool_outputs"]),
        "result": dict(tool_result) if tool_result is not None else {},
        "output": str(tool_result.get("summary", "")).strip() if tool_result is not None else "",
        "facts": dict(tool_result.get("facts") or {}) if tool_result is not None else {},
    }
    if node.rule is None or not node.rule.inputs:
        return payload
    resolved = dict(payload)
    for input_name, source_path in node.rule.inputs.items():
        resolved[input_name] = _resolve_by_path(payload, source_path)
    return resolved


def _resolve_by_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for segment in str(path or "").split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        return None
    return current


def _resolve_runtime_value(path: str, blackboard: dict[str, Any]) -> Any:
    normalized = str(path or "").strip()
    if not normalized:
        return None
    namespaces = {
        "context": dict(blackboard.get("context") or {}),
        "inputs": dict(blackboard.get("context") or {}),
        "variables": dict(blackboard.get("variables") or {}),
        "tool_outputs": dict(blackboard.get("tool_outputs") or {}),
        "observations": dict(blackboard.get("observations") or {}),
    }
    if "." in normalized:
        head = normalized.split(".", 1)[0]
        if head in namespaces:
            return _resolve_by_path(namespaces, normalized)
    for namespace_name in ("context", "variables", "tool_outputs", "observations"):
        value = _resolve_by_path({"value": namespaces[namespace_name]}, f"value.{normalized}")
        if value is not None:
            return value
    return None


def _record_observation(
    node: BTNodeSpec,
    *,
    blackboard: dict[str, Any],
    passed: bool,
    tool_result: ToolResult | None,
    rule_result: Any,
) -> None:
    blackboard["observations"][node.node_id] = passed
    if tool_result is not None:
        blackboard["variables"][f"{node.node_id}.facts"] = dict(tool_result.get("facts") or {})
        blackboard["variables"][f"{node.node_id}.summary"] = str(tool_result.get("summary") or "").strip()
    if rule_result is not None:
        blackboard["variables"][f"{node.node_id}.rule"] = asdict(rule_result)


def _snapshot_blackboard(blackboard: dict[str, Any]) -> BlackboardSnapshot:
    return BlackboardSnapshot(
        current_node_id=str(blackboard.get("current_node_id") or "").strip(),
        observations=dict(blackboard.get("observations") or {}),
        variables=dict(blackboard.get("variables") or {}),
        tool_outputs=dict(blackboard.get("tool_outputs") or {}),
    )


def _build_confirmation(
    node: BTNodeSpec,
    *,
    blackboard: dict[str, Any],
    tool_result: ToolResult | None = None,
) -> dict[str, Any]:
    confirmation = _node_confirmation(node)
    mode = str(confirmation.get("mode") or "approve").strip().lower()
    input_spec = dict(confirmation.get("input") or {}) if isinstance(confirmation.get("input"), dict) else {}
    if mode == "select":
        resolved_options = _resolve_confirmation_options(input_spec, blackboard=blackboard, tool_result=tool_result)
        if resolved_options:
            input_spec["options"] = resolved_options
        else:
            return _build_text_fallback_request(node, confirmation)
    return {
        "node_path": node.node_id,
        "message": str(confirmation.get("message") or node.name).strip(),
        "options": [] if mode in {"input", "select"} else ["继续执行"],
        "resume_from_step": "playbook_execution",
        "input": input_spec,
        "output": confirmation.get("output"),
        "mode": mode,
        "kind": "input" if mode in {"input", "select"} else "confirmation",
        "payload": {
            "playbook_id": blackboard["active_playbooks"][-1],
            "tool_result": dict(tool_result) if tool_result is not None else None,
        },
    }


def _build_input_request(node: BTNodeSpec, prompt: str) -> dict[str, Any]:
    output_spec = dict((_node_confirmation(node) or {}).get("output") or {})
    return {
        "node_path": node.node_id,
        "message": prompt,
        "options": [],
        "resume_from_step": "playbook_execution",
        "input": {
            "type": "text",
            "label": node.name,
            "allow_empty": False,
        },
        "output": output_spec or {"store_as": node.node_id, "type": "raw_input"},
        "mode": "input",
        "kind": "input",
        "payload": {},
    }


def _build_text_fallback_request(node: BTNodeSpec, confirmation: dict[str, Any]) -> dict[str, Any]:
    input_spec = dict(confirmation.get("input") or {}) if isinstance(confirmation.get("input"), dict) else {}
    output_spec = dict(confirmation.get("output") or {}) if isinstance(confirmation.get("output"), dict) else {}
    return {
        "node_path": node.node_id,
        "message": str(confirmation.get("message") or node.name).strip(),
        "options": [],
        "resume_from_step": "playbook_execution",
        "input": {
            "type": "text",
            "label": str(input_spec.get("label") or node.name).strip() or node.name,
            "placeholder": str(input_spec.get("placeholder") or "").strip(),
            "help_text": str(input_spec.get("help_text") or "").strip(),
            "allow_empty": bool(input_spec.get("allow_empty", False)),
        },
        "output": output_spec or {"store_as": node.node_id, "type": "raw_input"},
        "mode": "input",
        "kind": "input",
        "payload": {},
    }


def _should_skip_for_resume(node: BTNodeSpec, blackboard: dict[str, Any]) -> bool:
    resume = blackboard.get("resume") or {}
    if not resume or resume.get("consumed"):
        return False
    target_node_id = str(resume.get("node_id") or "").strip()
    if not target_node_id:
        return False
    return not _subtree_contains(node, target_node_id)


def _subtree_contains(node: BTNodeSpec, target_node_id: str) -> bool:
    if node.node_id == target_node_id:
        return True
    return any(_subtree_contains(child, target_node_id) for child in node.children)


def _resume_active_for_node(blackboard: dict[str, Any], node: BTNodeSpec) -> bool:
    resume = blackboard.get("resume") or {}
    return bool(resume) and not bool(resume.get("consumed")) and str(resume.get("node_id") or "").strip() == node.node_id


def _get_resume_for_node(blackboard: dict[str, Any], node: BTNodeSpec) -> dict[str, Any] | None:
    if not _resume_active_for_node(blackboard, node):
        return None
    blackboard["resume"]["consumed"] = True
    return dict(blackboard["resume"])


def _load_resume_tool_result(resume_entry: dict[str, Any] | None) -> ToolResult | None:
    if not isinstance(resume_entry, dict):
        return None
    tool_result = resume_entry.get("tool_result")
    if not isinstance(tool_result, dict):
        return None
    return build_tool_result(
        call_id=str(tool_result.get("call_id") or "").strip(),
        tool_name=str(tool_result.get("tool_name") or "").strip(),
        success=bool(tool_result.get("success", False)),
        status=str(tool_result.get("status") or "").strip(),
        facts=dict(tool_result.get("facts") or {}) if isinstance(tool_result.get("facts"), dict) else {},
        summary=str(tool_result.get("summary") or "").strip(),
        data=dict(tool_result.get("data") or {}) if isinstance(tool_result.get("data"), dict) else {},
        error=str(tool_result.get("error") or "").strip(),
        raw_output=str(tool_result.get("raw_output") or "").strip(),
    )


def _apply_confirmation_output(node: BTNodeSpec, *, blackboard: dict[str, Any], resume_entry: dict[str, Any]) -> None:
    output_spec = dict((_node_confirmation(node) or {}).get("output") or {})
    if not output_spec:
        return
    store_as = str(output_spec.get("store_as") or node.node_id).strip() or node.node_id
    blackboard["context"][store_as] = _resolve_resume_value(node=node, resume_entry=resume_entry)


def _resolve_resume_value(*, node: BTNodeSpec, resume_entry: dict[str, Any]) -> Any:
    confirmation = _node_confirmation(node)
    output_spec = dict(confirmation.get("output") or {})
    input_spec = dict(confirmation.get("input") or {})
    if isinstance(resume_entry.get("input"), dict):
        input_spec.update(dict(resume_entry["input"]))
    output_type = str(output_spec.get("type") or "boolean").strip().lower()
    raw_value = resume_entry.get("user_response")
    if output_type == "boolean":
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip().lower() not in {"false", "0", "no", "cancel"}
        return True
    if output_type in {"selected_option_value", "selected_option_label", "selected_option_index"}:
        selected = _resolve_selected_option(raw_value, input_spec)
        if selected is None:
            return raw_value
        if output_type == "selected_option_label":
            return selected["label"]
        if output_type == "selected_option_index":
            return selected["index"]
        return selected["value"]
    if output_type == "selected_option_index":
        try:
            return int(str(raw_value).strip())
        except ValueError:
            return 0
    return raw_value


def _resolve_confirmation_options(
    input_spec: dict[str, Any],
    *,
    blackboard: dict[str, Any],
    tool_result: ToolResult | None,
) -> list[dict[str, Any]]:
    direct_options = _normalize_select_options(input_spec.get("options"))
    if direct_options:
        return direct_options
    options_source = input_spec.get("options_source") if isinstance(input_spec.get("options_source"), dict) else {}
    if not options_source:
        return []
    context_key = str(options_source.get("from_context") or "").strip()
    if context_key:
        value = blackboard["context"].get(context_key)
        list_key = str(options_source.get("list_key") or "").strip()
        if list_key:
            value = _resolve_by_path({"value": value}, f"value.{list_key}")
        return _normalize_select_options(value)
    source_field = str(options_source.get("field") or "output").strip() or "output"
    source_parser = str(options_source.get("parser") or "").strip().lower()
    payload = {
        "output": str(tool_result.get("summary", "")).strip() if tool_result is not None else "",
        "result": dict(tool_result) if tool_result is not None else {},
        "facts": dict(tool_result.get("facts") or {}) if tool_result is not None else {},
    }
    value = _resolve_by_path(payload, source_field)
    if source_parser == "string_list":
        return _normalize_select_options(_parse_string_list_options(value))
    return _normalize_select_options(value)


def _parse_string_list_options(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in re.split(r"[\r\n,]+", text) if item.strip()]


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


def _resolve_selected_option(raw_value: Any, input_spec: dict[str, Any]) -> dict[str, Any] | None:
    options = _normalize_select_options(input_spec.get("options"))
    if not options:
        return None
    response = str(raw_value or "").strip()
    if not response and bool(input_spec.get("auto_select_if_single")) and len(options) == 1:
        return options[0]
    if response.isdigit():
        selected_index = int(response)
        for option in options:
            if option["index"] == selected_index or option["index"] + 1 == selected_index:
                return option
    for option in options:
        if response in {str(option["label"]).strip(), str(option["value"]).strip()}:
            return option
    return None
