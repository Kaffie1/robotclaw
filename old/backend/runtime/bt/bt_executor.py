from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import py_trees

from ...core.models import ApiError
from ..rules import build_playbook_rule_context
from ..workflow.confirmation import (
    PLAYBOOK_CONTEXT_KEY,
    PLAYBOOK_CONTEXT_KEYS_KEY,
    PLAYBOOK_CONTEXT_SOURCES_KEY,
    RUNTIME_CONTEXT_KEY,
    sync_playbook_context_view,
)
from .executor import (
    PlaybookConfirmationRequired,
    execute_playbook,
    run_leaf_step,
    short_text,
    update_observations,
)
from ..playbooks.loader import find_playbook_by_id


def _normalize_status(value: str) -> py_trees.common.Status:
    """将字符串类型的状态转换为 py_trees.common.Status 枚举值，支持 "success"、"running" 和 "failure" 三种状态，默认为 FAILURE"""
    normalized = str(value or "").strip().lower()
    if normalized == "success":
        return py_trees.common.Status.SUCCESS
    if normalized == "running":
        return py_trees.common.Status.RUNNING
    return py_trees.common.Status.FAILURE


def _is_resume_safe_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_is_resume_safe_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_resume_safe_value(item) for key, item in value.items())
    return False


def _build_resume_runtime_context(tool_context: dict[str, Any]) -> dict[str, Any]:
    runtime_context = tool_context.get(RUNTIME_CONTEXT_KEY)
    if not isinstance(runtime_context, dict):
        return {}
    return {
        str(key): value
        for key, value in runtime_context.items()
        if isinstance(key, str) and _is_resume_safe_value(value)
    }


def _is_descendant_node_path(node_path: str, descendant_path: str) -> bool:
    """判断 descendant_path 是否是 node_path 的后代路径，要求 descendant_path 以 node_path 开头，并且两者之间以点号分隔"""
    normalized_node_path = str(node_path or "").strip()
    normalized_descendant_path = str(descendant_path or "").strip()
    return bool(normalized_node_path and normalized_descendant_path and normalized_descendant_path.startswith(f"{normalized_node_path}."))


def _build_node_status(
    node_path: str,
    completed_nodes: dict[str, dict[str, Any]],
    active_node_path: str,
    pending_confirmation: dict[str, Any] | None,
) -> str:
    """根据当前节点路径、已完成节点、正在执行的节点路径和待确认节点，构建当前节点的状态，
        状态包括 "waiting_confirmation"、"running"、"success"、"failure" 和 "idle" 五种可能"""
    pending_node_path = str((pending_confirmation or {}).get("node_path") or "").strip()
    if pending_node_path == node_path:
        return "waiting_confirmation"
    if active_node_path == node_path:
        return "running"
    completed = completed_nodes.get(node_path)
    if isinstance(completed, dict):
        return "success" if bool(completed.get("passed")) else "failure"
    if pending_node_path and _is_descendant_node_path(node_path, pending_node_path):
        return "running"
    if active_node_path and _is_descendant_node_path(node_path, active_node_path):
        return "running"
    return "idle"


def _build_tree_state(
    node_spec: dict[str, Any],
    *,
    node_path: str,
    completed_nodes: dict[str, dict[str, Any]],
    active_node_path: str,
    active_node_message: str,
    pending_confirmation: dict[str, Any] | None,
    node_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    children_specs = node_spec.get("children") if isinstance(node_spec.get("children"), list) else []
    children: list[dict[str, Any]] = []
    for index, child_spec in enumerate(children_specs):
        if isinstance(child_spec, dict):
            children.append(
                _build_tree_state(
                    child_spec,
                    node_path=f"{node_path}.children[{index}]",
                    completed_nodes=completed_nodes,
                    active_node_path=active_node_path,
                    active_node_message=active_node_message,
                    pending_confirmation=pending_confirmation,
                    node_states=node_states,
                )
            )
    status = _build_node_status(node_path, completed_nodes, active_node_path, pending_confirmation)
    completed = completed_nodes.get(node_path)
    node_state = {
        "node_path": node_path,
        "name": str(node_spec.get("name") or node_spec.get("tool_name") or node_spec.get("playbook_id") or node_spec.get("target_playbook_id") or "").strip(),
        "display_name": str(node_spec.get("display_name") or node_spec.get("message") or "").strip(),
        "node_type": str(node_spec.get("type") or "").strip().lower(),
        "status": status,
        "passed": None if not isinstance(completed, dict) else bool(completed.get("passed")),
        "message": "",
        "children": children,
    }
    if status == "waiting_confirmation":
        node_state["message"] = str((pending_confirmation or {}).get("message") or "").strip()
    elif active_node_path == node_path:
        node_state["message"] = str(active_node_message or (completed or {}).get("output") or "").strip()
    elif isinstance(completed, dict):
        node_state["message"] = str(completed.get("output") or "").strip()
    node_states[node_path] = {
        "status": node_state["status"],
        "passed": node_state["passed"],
        "message": node_state["message"],
        "node_type": node_state["node_type"],
        "name": node_state["name"],
        "display_name": node_state["display_name"],
    }
    return node_state


@dataclass
class BehaviourTreeState:
    playbook: dict[str, Any]
    tool_context: dict[str, Any]
    visited_ids: set[str]
    depth: int
    max_depth: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, bool | None] = field(default_factory=dict)
    recent_tasks: list[dict[str, Any]] = field(default_factory=list)
    sub_playbooks: list[dict[str, Any]] = field(default_factory=list)
    conclusion: str = ""
    next_action: str = ""
    completed_nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_child_resumes: dict[str, dict[str, Any]] = field(default_factory=dict)
    interrupt_state: dict[str, Any] = field(default_factory=dict)
    active_node_path: str = ""
    active_node_message: str = ""
    pending_confirmation: dict[str, Any] | None = None
    executed: bool = False
    passed: bool | None = None
    status_reporter: Callable[[dict[str, Any]], None] | None = None
    tree_status_reporter: Callable[[dict[str, Any]], None] | None = None

    def to_resume_state(self) -> dict[str, Any]:
        """构建当前执行状态的可恢复状态字典，包括 playbook_context、completed_nodes、pending_child_resumes 和 interrupt_state 四个部分，供后续恢复执行时使用"""
        return {
            "playbook_context": dict(self.tool_context.get(PLAYBOOK_CONTEXT_KEY) or {}),
            "runtime_context": _build_resume_runtime_context(self.tool_context),
            "completed_nodes": dict(self.completed_nodes),
            "pending_child_resumes": dict(self.pending_child_resumes),
            "interrupt_state": dict(self.interrupt_state),
        }

    def to_execution_snapshot(self) -> dict[str, Any]:
        """构建当前执行状态的快照，包括 playbook 基本信息、执行步骤、观察结果、结论和下一步行动，以及可选的行为树节点状态"""
        payload = {
            "playbook_id": str(self.playbook.get("id") or "").strip(),
            "playbook_title": str(self.playbook.get("title") or "").strip(),
            "executed": self.executed,
            "playbook_context": dict(self.tool_context.get(PLAYBOOK_CONTEXT_KEY) or {}),
            "steps": list(self.steps),
            "observations": dict(self.observations),
            "conclusion": self.conclusion,
            "next_action": self.next_action,
            "recent_tasks": list(self.recent_tasks),
            "sub_playbooks": list(self.sub_playbooks),
            "sub_playbook": self.sub_playbooks[-1] if self.sub_playbooks else None,
            "matched_context": self.playbook,
            "active_node_path": self.active_node_path,
            "active_node_message": self.active_node_message,
            "pending_confirmation": dict(self.pending_confirmation) if isinstance(self.pending_confirmation, dict) else None,
        }
        if self.passed is not None:
            payload["passed"] = self.passed
        root_spec = self.playbook.get("root") if isinstance(self.playbook.get("root"), dict) else None
        node_states: dict[str, dict[str, Any]] = {}
        payload["tree_state"] = (
            _build_tree_state(
                root_spec,
                node_path="root",
                completed_nodes=self.completed_nodes,
                active_node_path=self.active_node_path,
                active_node_message=self.active_node_message,
                pending_confirmation=self.pending_confirmation,
                node_states=node_states,
            )
            if isinstance(root_spec, dict)
            else None
        )
        payload["node_states"] = node_states
        return payload

    def emit_status_update(self) -> None:
        """调用状态报告函数将当前的执行快照和节点状态更新到外部。"""
        snapshot = self.to_execution_snapshot()
        if callable(self.status_reporter):
            self.status_reporter(snapshot)
        if callable(self.tree_status_reporter):
            self.tree_status_reporter(snapshot)

class ToolBehaviour(py_trees.behaviour.Behaviour):
    def __init__(self, node_spec: dict[str, Any], state: BehaviourTreeState, *, node_kind: str, node_path: str) -> None:
        super().__init__(name=str(node_spec.get("name") or node_spec.get("tool_name") or node_kind))
        self.node_spec = dict(node_spec)
        self.state = state
        self.node_kind = node_kind
        self.node_path = node_path

    def update(self) -> py_trees.common.Status:
        cached = self.state.completed_nodes.get(self.node_path)
        if isinstance(cached, dict):
            return py_trees.common.Status.SUCCESS if bool(cached.get("passed")) else py_trees.common.Status.FAILURE
        self.state.active_node_path = self.node_path
        self.state.active_node_message = str(self.node_spec.get("display_name") or self.node_spec.get("name") or self.node_spec.get("tool_name") or "").strip()
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        try:
            result = run_leaf_step(
                self.node_spec,
                self.state.tool_context,
                playbook_id=str(self.state.playbook.get("id") or "").strip(),
                playbook_title=str(self.state.playbook.get("title") or "").strip(),
                node_path=self.node_path,
            )
        except PlaybookConfirmationRequired as interrupt:
            self.state.interrupt_state = {
                "type": "confirmation",
                "node_path": self.node_path,
                "node_name": str(self.node_spec.get("name") or self.node_spec.get("tool_name") or "").strip(),
                "message": str(interrupt.request.get("message") or "").strip(),
            }
            self.state.pending_confirmation = dict(interrupt.request)
            self.state.active_node_message = str(interrupt.request.get("message") or self.state.active_node_message).strip()
            self.state.emit_status_update()
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = str(getattr(exc, "message", "") or str(exc) or "节点执行失败").strip()
            result = {
                "name": str(self.node_spec.get("name") or self.node_spec.get("tool_name") or "").strip(),
                "tool_name": str(self.node_spec.get("tool_name") or "").strip(),
                "arguments": self.node_spec.get("arguments") if isinstance(self.node_spec.get("arguments"), dict) else {},
                "output": error_message,
                "raw_result": {"ok": False, "error": error_message},
                "passed": False,
                "assert_ref": str(self.node_spec.get("assert_ref") or self.node_spec.get("expect") or "").strip(),
                "node_path": self.node_path,
                "wait_seconds": max(int(self.node_spec.get("wait_seconds") or 0), 0),
                "confirm_times": max(int(self.node_spec.get("confirm_times") or 1), 1),
                "attempts": [],
                "failure_message": error_message,
            }
        result["node_type"] = self.node_kind
        self.state.steps.append(result)
        update_observations(self.state.observations, result)
        self.state.completed_nodes[self.node_path] = dict(result)
        self.state.interrupt_state = {}
        self.state.active_node_path = ""
        self.state.active_node_message = ""
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        if bool(result.get("passed")):
            success_message = str(self.node_spec.get("success_message") or "").strip()
            if success_message:
                self.state.conclusion = success_message
            return py_trees.common.Status.SUCCESS
        failure_message = str(self.node_spec.get("failure_message") or result.get("failure_message") or "").strip()
        if failure_message:
            self.state.conclusion = failure_message
            self.state.next_action = failure_message
        return py_trees.common.Status.FAILURE


class ResultBehaviour(py_trees.behaviour.Behaviour):
    def __init__(self, node_spec: dict[str, Any], state: BehaviourTreeState, *, node_path: str) -> None:
        super().__init__(name=str(node_spec.get("name") or "result"))
        self.node_spec = dict(node_spec)
        self.state = state
        self.node_path = node_path

    def update(self) -> py_trees.common.Status:
        cached = self.state.completed_nodes.get(self.node_path)
        if isinstance(cached, dict):
            return py_trees.common.Status.SUCCESS if bool(cached.get("passed")) else py_trees.common.Status.FAILURE
        self.state.active_node_path = self.node_path
        self.state.active_node_message = str(self.node_spec.get("message") or self.name).strip()
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        status = _normalize_status(self.node_spec.get("status") or "failure")
        message = str(self.node_spec.get("message") or "").strip()
        step = {
            "name": self.name,
            "tool_name": "",
            "arguments": {},
            "output": message,
            "passed": status == py_trees.common.Status.SUCCESS,
            "node_type": "result",
            "result_status": status.value,
            "node_path": self.node_path,
        }
        self.state.steps.append(step)
        self.state.completed_nodes[self.node_path] = dict(step)
        self.state.interrupt_state = {}
        self.state.active_node_path = ""
        self.state.active_node_message = ""
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        if message:
            self.state.conclusion = message
            self.state.next_action = message
        return status


class CallPlaybookBehaviour(py_trees.behaviour.Behaviour):
    def __init__(self, node_spec: dict[str, Any], state: BehaviourTreeState, *, node_path: str) -> None:
        super().__init__(name=str(node_spec.get("name") or node_spec.get("playbook_id") or "call_playbook"))
        self.node_spec = dict(node_spec)
        self.state = state
        self.node_path = node_path

    def _rebase_child_node_path(self, child_node_path: str) -> str:
        """将子节点路径转换为相对于当前节点路径的格式，如果子节点路径以 "root" 开头，则替换为当前节点路径，否则保持不变"""
        normalized_path = str(child_node_path or "").strip()
        child_root_path = f"{self.node_path}.children[0]"
        if not normalized_path or normalized_path == "root":
            return child_root_path
        if normalized_path.startswith("root."):
            return f"{child_root_path}{normalized_path[4:]}"
        return normalized_path

    def _build_live_child_step(self, playbook_id: str, child_result: dict[str, Any]) -> dict[str, Any]:
        """构建当前调用的子 playbook 的执行结果步骤，包括子 playbook 的结论或下一步行动作为输出，以及子 playbook 的执行结果作为 raw_result，供后续在父 playbook 中展示和使用"""
        return {
            "name": self.name,
            "tool_name": "call_playbook",
            "arguments": {"playbook_id": playbook_id},
            "output": short_text(child_result.get("conclusion") or child_result.get("next_action") or ""),
            "passed": bool(child_result.get("passed")),
            "node_type": "call_playbook",
            "sub_playbook": child_result,
            "called_playbook_id": playbook_id,
            "node_path": self.node_path,
        }

    def _build_live_child_snapshot(self, playbook_id: str, child_result: dict[str, Any]) -> dict[str, Any]:
        """构建当前调用的子 playbook 的执行快照，包括子 playbook 的执行结果步骤和当前节点状态，供在等待用户确认时展示"""
        snapshot = self.state.to_execution_snapshot()
        snapshot["steps"] = [*self.state.steps, self._build_live_child_step(playbook_id, child_result)]
        snapshot["sub_playbooks"] = [*self.state.sub_playbooks, child_result]
        snapshot["sub_playbook"] = child_result
        if child_result.get("conclusion"):
            snapshot["conclusion"] = child_result.get("conclusion")
        if child_result.get("next_action"):
            snapshot["next_action"] = child_result.get("next_action")
        return snapshot

    def _build_child_status_reporter(self, playbook_id: str) -> Callable[[dict[str, Any]], None]:
        """构建一个状态报告函数，用于子 playbook 在执行过程中报告状态更新时，将子 playbook 的执行快照和当前节点状态更新到父 playbook 的状态中，并触发父 playbook 的状态更新函数来通知外部当前的执行状态，支持 pending_confirmation 来指示当前是否在等待用户确认"""
        def reporter(child_payload: dict[str, Any]) -> None:
            if not callable(self.state.status_reporter):
                return
            rebased_payload = dict(child_payload)
            rebased_pending = child_payload.get("pending_confirmation") if isinstance(child_payload, dict) else None
            if isinstance(rebased_pending, dict):
                rebased_pending = dict(rebased_pending)
                rebased_pending["node_path"] = self._rebase_child_node_path(rebased_pending.get("node_path", ""))
            rebased_payload["pending_confirmation"] = rebased_pending
            rebased_payload["active_node_path"] = self._rebase_child_node_path(child_payload.get("active_node_path", ""))
            child_snapshot = self._build_live_child_snapshot(playbook_id, rebased_payload)
            child_snapshot["pending_confirmation"] = rebased_pending
            child_snapshot["active_node_path"] = rebased_payload["active_node_path"]
            child_snapshot["active_node_message"] = str(rebased_payload.get("active_node_message") or "").strip()
            self.state.status_reporter(child_snapshot)

        return reporter

    def update(self) -> py_trees.common.Status:
        cached = self.state.completed_nodes.get(self.node_path)
        if isinstance(cached, dict):
            return py_trees.common.Status.SUCCESS if bool(cached.get("passed")) else py_trees.common.Status.FAILURE
        self.state.active_node_path = self.node_path
        self.state.active_node_message = str(self.node_spec.get("name") or self.node_spec.get("playbook_id") or "call_playbook").strip()
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        playbook_id = str(self.node_spec.get("playbook_id") or self.node_spec.get("target_playbook_id") or "").strip()
        if not playbook_id:
            raise ApiError(f"行为树节点缺少 playbook_id: {self.name}")
        child_playbook = find_playbook_by_id(playbook_id)
        if child_playbook is None:
            raise ApiError(f"未找到子 playbook: {playbook_id}")
        child_resume_state = self.state.pending_child_resumes.get(self.node_path)
        child_result = execute_playbook(
            child_playbook,
            self.state.tool_context,
            visited_ids=set(self.state.visited_ids),
            depth=self.state.depth + 1,
            max_depth=self.state.max_depth,
            resume_state=child_resume_state,
            status_reporter=self._build_child_status_reporter(playbook_id),
        )
        if isinstance(child_result.get("pending_confirmation"), dict):
            resume_state = child_result.get("resume_state")
            if isinstance(resume_state, dict):
                self.state.pending_child_resumes[self.node_path] = resume_state
            self.state.interrupt_state = {
                "type": "child_confirmation",
                "node_path": self.node_path,
                "node_name": str(self.node_spec.get("name") or self.node_spec.get("playbook_id") or "").strip(),
                "message": str((child_result.get("pending_confirmation") or {}).get("message") or "").strip(),
            }
            pending_confirmation = dict(child_result.get("pending_confirmation") or {})
            pending_confirmation["node_path"] = self._rebase_child_node_path(pending_confirmation.get("node_path", ""))
            self.state.pending_confirmation = pending_confirmation
            self.state.active_node_message = str(pending_confirmation.get("message") or self.state.active_node_message).strip()
            self.state.emit_status_update()
            raise PlaybookConfirmationRequired(pending_confirmation)
        self.state.pending_child_resumes.pop(self.node_path, None)
        self.state.sub_playbooks.append(child_result)
        step = self._build_live_child_step(playbook_id, child_result)
        self.state.steps.append(step)
        self.state.completed_nodes[self.node_path] = dict(step)
        self.state.interrupt_state = {}
        self.state.active_node_path = ""
        self.state.active_node_message = ""
        self.state.pending_confirmation = None
        self.state.emit_status_update()
        self.state.observations.update(
            {
                key: value
                for key, value in (child_result.get("observations") or {}).items()
                if key not in self.state.observations or value is not None
            }
        )
        if bool(child_result.get("passed")):
            success_message = str(self.node_spec.get("success_message") or "").strip()
            if success_message:
                self.state.conclusion = success_message
            return py_trees.common.Status.SUCCESS
        failure_message = str(child_result.get("conclusion") or child_result.get("next_action") or self.node_spec.get("failure_message") or "").strip()
        if failure_message:
            self.state.conclusion = failure_message
            self.state.next_action = failure_message
        return py_trees.common.Status.FAILURE


def _build_bt_node(node_spec: dict[str, Any], state: BehaviourTreeState, *, node_path: str) -> py_trees.behaviour.Behaviour:
    node_type = str(node_spec.get("type") or "").strip().lower()
    name = str(node_spec.get("name") or node_type or "node").strip()
    if node_type == "sequence":
        node = py_trees.composites.Sequence(
            name=name,
            memory=bool(node_spec.get("memory", False)),
        )
        children = node_spec.get("children") if isinstance(node_spec.get("children"), list) else []
        for index, child in enumerate(children):
            if isinstance(child, dict):
                node.add_child(_build_bt_node(child, state, node_path=f"{node_path}.children[{index}]"))
        return node
    if node_type == "selector":
        node = py_trees.composites.Selector(
            name=name,
            memory=bool(node_spec.get("memory", False)),
        )
        children = node_spec.get("children") if isinstance(node_spec.get("children"), list) else []
        for index, child in enumerate(children):
            if isinstance(child, dict):
                node.add_child(_build_bt_node(child, state, node_path=f"{node_path}.children[{index}]"))
        return node
    if node_type == "condition":
        return ToolBehaviour(node_spec, state, node_kind="condition", node_path=node_path)
    if node_type == "action":
        return ToolBehaviour(node_spec, state, node_kind="action", node_path=node_path)
    if node_type == "call_playbook":
        return CallPlaybookBehaviour(node_spec, state, node_path=node_path)
    if node_type == "result":
        return ResultBehaviour(node_spec, state, node_path=node_path)
    raise ApiError(f"不支持的行为树节点类型: {node_type}")


def execute_tree_playbook(
    playbook: dict[str, Any],
    tool_context: dict[str, Any] | None,
    *,
    visited_ids: set[str] | None = None,
    depth: int = 0,
    max_depth: int = 4,
    resume_state: dict[str, Any] | None = None,
    status_reporter: Callable[[dict[str, Any]], None] | None = None,
    tree_status_reporter: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    playbook_id = str(playbook.get("id") or "").strip()
    playbook_title = str(playbook.get("title") or "").strip()
    playbook_source_path = str(playbook.get("source_path") or "").strip()
    playbook_rules_source_path = str(playbook.get("rules_source_path") or "").strip()
    if not playbook_id:
        return {"playbook_id": "", "playbook_title": playbook_title, "executed": False, "reason": "playbook 缺少 id", "matched_context": playbook}
    if depth > max_depth:
        return {"playbook_id": playbook_id, "playbook_title": playbook_title, "executed": False, "reason": "playbook 嵌套层级超过上限", "matched_context": playbook}
    # 防止循环引用导致的无限递归，visited_ids 用于记录当前执行路径上已经访问过的 playbook_id，如果再次访问到已经访问过的 playbook_id，则说明存在循环引用，应该停止执行并返回错误信息
    normalized_visited_ids = set(visited_ids or set())
    if playbook_id in normalized_visited_ids:
        return {"playbook_id": playbook_id, "playbook_title": playbook_title, "executed": False, "reason": "检测到 playbook 循环引用", "matched_context": playbook}
    normalized_visited_ids.add(playbook_id)
    raw_context_schema = playbook.get("context_schema")
    declared_context_keys = [
        str(key or "").strip()
        for key in (raw_context_schema or {}).keys()
        if str(key or "").strip()
    ] if isinstance(raw_context_schema, dict) else []
    declared_context_sources = {
        str(key or "").strip(): str((spec or {}).get("source") or "").strip().lower()
        for key, spec in (raw_context_schema or {}).items()
        if str(key or "").strip() and isinstance(spec, dict)
    } if isinstance(raw_context_schema, dict) else {}
    base_tool_context = {
        **dict(tool_context or {}),
        "playbook_id": playbook_id,
        "playbook_title": playbook_title,
        "playbook_source_path": playbook_source_path,
        "playbook_rules_source_path": playbook_rules_source_path,
    }
    resumed_runtime_context = dict(resume_state.get("runtime_context") or {}) if isinstance(resume_state, dict) else {}
    base_tool_context[RUNTIME_CONTEXT_KEY] = {
        **(dict(base_tool_context.get(RUNTIME_CONTEXT_KEY) or {}) if isinstance(base_tool_context.get(RUNTIME_CONTEXT_KEY), dict) else {}),
        **(resumed_runtime_context if isinstance(resumed_runtime_context, dict) else {}),
        "session": base_tool_context.get("session"),
        "session_id": base_tool_context.get("session_id"),
        "playbook_id": playbook_id,
        "playbook_title": playbook_title,
    }
    resumed_playbook_context = dict(resume_state.get("playbook_context") or {}) if isinstance(resume_state, dict) else {}
    initial_playbook_context = dict(resumed_playbook_context)
    for key in declared_context_keys:
        if declared_context_sources.get(key) == "runtime":
            continue
        if key not in base_tool_context:
            continue
        resumed_value = initial_playbook_context.get(key)
        if key not in initial_playbook_context or resumed_value is None or (isinstance(resumed_value, str) and not resumed_value.strip()):
            initial_playbook_context[key] = base_tool_context.get(key)
    base_tool_context[PLAYBOOK_CONTEXT_KEY] = initial_playbook_context
    base_tool_context[PLAYBOOK_CONTEXT_KEYS_KEY] = declared_context_keys
    base_tool_context[PLAYBOOK_CONTEXT_SOURCES_KEY] = declared_context_sources
    sync_playbook_context_view(base_tool_context)
    playbook_context = build_playbook_rule_context(base_tool_context)
    sync_playbook_context_view(playbook_context)
    state = BehaviourTreeState(
        playbook=playbook,
        tool_context=playbook_context,
        visited_ids=normalized_visited_ids,
        depth=depth,
        max_depth=max_depth,
        completed_nodes=dict(resume_state.get("completed_nodes") or {}) if isinstance(resume_state, dict) else {},
        pending_child_resumes=dict(resume_state.get("pending_child_resumes") or {}) if isinstance(resume_state, dict) else {},
        interrupt_state=dict(resume_state.get("interrupt_state") or {}) if isinstance(resume_state, dict) else {},
        status_reporter=status_reporter,
        tree_status_reporter=tree_status_reporter,
    )
    root_spec = playbook.get("root")
    if not isinstance(root_spec, dict):
        return {"playbook_id": playbook_id, "playbook_title": playbook_title, "executed": False, "reason": "行为树 playbook 缺少 root", "matched_context": playbook}
    root = _build_bt_node(root_spec, state, node_path="root")
    tree = py_trees.trees.BehaviourTree(root)
    state.emit_status_update()
    try:
        tree.tick()
    except PlaybookConfirmationRequired as interrupt:
        state.pending_confirmation = dict(interrupt.request)
        state.executed = False
        state.passed = None
        state.emit_status_update()
        interrupted_snapshot = state.to_execution_snapshot()
        return {
            **interrupted_snapshot,
            "interrupted": True,
            "interrupt_state": dict(state.interrupt_state),
            "pending_confirmation": interrupt.request,
            "resume_state": state.to_resume_state(),
        }
    passed = root.status == py_trees.common.Status.SUCCESS
    if not state.conclusion:
        state.conclusion = "playbook 执行完成" if passed else "playbook 执行完成，但仍有未通过的判定"
    if not state.next_action:
        state.next_action = "继续观察当前状态" if passed else "查看未通过的节点并继续处理"
    state.executed = True
    state.passed = passed
    state.pending_confirmation = None
    state.emit_status_update()
    return state.to_execution_snapshot()
