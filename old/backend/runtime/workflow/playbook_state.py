from __future__ import annotations

import copy
import json
import threading
import time
from collections import deque
from collections.abc import Iterator
from typing import Any

from ...core.shared import logger, normalize_message_content
from ..playbooks.loader import find_playbook_by_id

_state_lock = threading.RLock()
_DEFAULT_SESSION_KEY = "__default__"
_live_states: dict[str, dict[str, Any]] = {}
_live_events_by_session: dict[str, deque[dict[str, Any]]] = {}
_state_changed = threading.Condition(_state_lock)


def _now() -> float:
    return time.time()


def _clone_payload(value: Any) -> Any:
    return copy.deepcopy(value)


def _normalize_session_key(session_id: str | None) -> str:
    normalized = normalize_message_content(session_id or "")
    return normalized or _DEFAULT_SESSION_KEY


def _empty_live_state() -> dict[str, Any]:
    return {
        "playbook": None,
        "playbook_execution": None,
        "pending_confirmation": None,
        "updated_at": 0.0,
        "version": 0,
    }


def _ensure_session_bucket(session_id: str | None) -> tuple[dict[str, Any], deque[dict[str, Any]]]:
    session_key = _normalize_session_key(session_id)
    state = _live_states.get(session_key)
    if state is None:
        state = _empty_live_state()
        _live_states[session_key] = state
    events = _live_events_by_session.get(session_key)
    if events is None:
        events = deque(maxlen=512)
        _live_events_by_session[session_key] = events
    return state, events


def _build_render_root(node: dict[str, Any] | None, *, visited_playbook_ids: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}

    visited = set(visited_playbook_ids or set())
    rendered_node = dict(node)
    children = node.get("children") if isinstance(node.get("children"), list) else []
    node_type = normalize_message_content(node.get("type", "")).lower()

    rendered_children = [
        _build_render_root(child, visited_playbook_ids=visited)
        for child in children
        if isinstance(child, dict)
    ]

    if node_type == "call_playbook":
        target_playbook_id = normalize_message_content(node.get("playbook_id") or node.get("target_playbook_id") or "")
        child_playbook = find_playbook_by_id(target_playbook_id)
        if target_playbook_id and isinstance(child_playbook, dict) and target_playbook_id not in visited:
            nested_visited = set(visited)
            nested_visited.add(target_playbook_id)
            child_root = _build_render_root(
                child_playbook.get("root") if isinstance(child_playbook.get("root"), dict) else {},
                visited_playbook_ids=nested_visited,
            )
            if child_root:
                rendered_children.append(child_root)
                rendered_node["expanded_playbook_id"] = target_playbook_id
                rendered_node["expanded_playbook_title"] = normalize_message_content(child_playbook.get("title", ""))

    if rendered_children:
        rendered_node["children"] = rendered_children
    else:
        rendered_node.pop("children", None)
    return rendered_node


def _build_render_root_from_playbook(playbook: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(playbook, dict):
        return {}
    playbook_id = normalize_message_content(playbook.get("id", ""))
    visited = {playbook_id} if playbook_id else set()
    root = playbook.get("root") if isinstance(playbook.get("root"), dict) else {}
    return _build_render_root(root, visited_playbook_ids=visited)


def _rebase_node_path(node_path: str, path_prefix: str) -> str:
    normalized_path = normalize_message_content(node_path)
    normalized_prefix = normalize_message_content(path_prefix) or "root"
    if not normalized_path:
        return normalized_prefix
    if normalized_path == "root":
        return normalized_prefix
    if normalized_path.startswith("root."):
        return f"{normalized_prefix}{normalized_path[4:]}"
    return normalized_path


def _collect_leaf_statuses(
    scripted_playbook: dict[str, Any] | None,
    *,
    path_prefix: str = "root",
) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    if not isinstance(scripted_playbook, dict):
        return statuses

    node_states = scripted_playbook.get("node_states") if isinstance(scripted_playbook.get("node_states"), dict) else {}
    for node_path, payload in node_states.items():
        if not isinstance(payload, dict):
            continue
        full_path = _rebase_node_path(node_path, path_prefix)
        if not full_path:
            continue
        raw_status = normalize_message_content(payload.get("status", "")).lower()
        normalized_status = ""
        if raw_status in {"running", "waiting_confirmation"}:
            normalized_status = "pending"
        elif raw_status == "success":
            normalized_status = "success"
        elif raw_status == "failure":
            normalized_status = "failed"
        elif raw_status in {"idle", "unstarted"}:
            normalized_status = "unstarted"
        if not normalized_status:
            continue
        statuses[full_path] = {
            "status": normalized_status,
            "passed": normalized_status == "success",
            "message": normalize_message_content(payload.get("message", "")),
        }

    for step in scripted_playbook.get("steps") or []:
        if not isinstance(step, dict):
            continue
        full_path = _rebase_node_path(step.get("node_path", ""), path_prefix)
        if not full_path:
            continue
        statuses[full_path] = {
            "status": "success" if bool(step.get("passed")) else "failed",
            "passed": bool(step.get("passed")),
            "message": normalize_message_content(
                step.get("success_message") or step.get("failure_message") or step.get("output") or ""
            ),
        }
        nested_playbook = step.get("sub_playbook")
        if isinstance(nested_playbook, dict):
            statuses.update(_collect_leaf_statuses(nested_playbook, path_prefix=f"{full_path}.children[0]"))
    return statuses


def build_matched_playbook_payload(playbook: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(playbook, dict):
        return None
    return {
        "id": normalize_message_content(playbook.get("id", "")),
        "type": normalize_message_content(playbook.get("type", "") or playbook.get("workflow_type", "")),
        "title": normalize_message_content(playbook.get("title", "")),
        "playbook_id": normalize_message_content(playbook.get("id", "")),
        "playbook_title": normalize_message_content(playbook.get("title", "")),
        "root": _build_render_root_from_playbook(playbook),
        "source_path": normalize_message_content(playbook.get("source_path", "")),
        "rules_source_path": normalize_message_content(playbook.get("rules_source_path", "")),
    }


def build_matched_playbook_payload_by_id(playbook_id: str, workflow_type: str | None = None) -> dict[str, Any] | None:
    if not playbook_id:
        return None
    return build_matched_playbook_payload(find_playbook_by_id(playbook_id, workflow_type=workflow_type))


def build_playbook_execution_payload(
    scripted_playbook: dict[str, Any] | None,
    *,
    pending_confirmation: dict[str, Any] | None = None,
    active_node_path: str = "",
    active_node_message: str = "",
) -> dict[str, Any] | None:
    if not isinstance(scripted_playbook, dict) and not isinstance(pending_confirmation, dict) and not active_node_path:
        return None

    matched_context = scripted_playbook.get("matched_context") if isinstance(scripted_playbook, dict) else {}
    root = _build_render_root_from_playbook(matched_context if isinstance(matched_context, dict) else None)
    leaf_statuses = _collect_leaf_statuses(scripted_playbook, path_prefix="root")
    script_passed = bool(scripted_playbook.get("passed")) if isinstance(scripted_playbook, dict) else False
    confirmation_node_path = normalize_message_content((pending_confirmation or {}).get("node_path", ""))
    current_active_node_path = normalize_message_content(active_node_path) or confirmation_node_path
    final_conclusion = normalize_message_content((scripted_playbook or {}).get("conclusion", ""))

    if current_active_node_path:
        leaf_statuses[current_active_node_path] = {
            "status": "pending",
            "passed": False,
            "message": normalize_message_content(active_node_message or (pending_confirmation or {}).get("message", "")),
        }

    node_statuses: dict[str, dict[str, Any]] = {}

    def mark_skipped(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        current = node_statuses.get(path)
        if current and current.get("status") != "unstarted":
            return
        node_statuses[path] = {
            "status": "skipped",
            "message": normalize_message_content(node.get("message") or node.get("success_message") or node.get("failure_message") or ""),
        }
        children = node.get("children") if isinstance(node.get("children"), list) else []
        for index, child in enumerate(children):
            mark_skipped(child, f"{path}.children[{index}]")

    def walk(node: Any, path: str = "root") -> str:
        if not isinstance(node, dict):
            return "unstarted"

        explicit = leaf_statuses.get(path)
        children = node.get("children") if isinstance(node.get("children"), list) else []
        node_type = normalize_message_content(node.get("type", "")).lower()

        if not children:
            status = normalize_message_content((explicit or {}).get("status", "")) or "unstarted"
            node_statuses[path] = {
                "status": status,
                "message": normalize_message_content((explicit or {}).get("message", "")),
            }
            return status

        child_statuses = []
        for index, child in enumerate(children):
            child_statuses.append(walk(child, f"{path}.children[{index}]"))

        def set_child_status(index: int, status: str) -> None:
            child_path = f"{path}.children[{index}]"
            current = normalize_message_content((node_statuses.get(child_path) or {}).get("status", ""))
            if current and current != "unstarted":
                return
            child_statuses[index] = status
            node_statuses[child_path] = {
                "status": status,
                "message": normalize_message_content(children[index].get("message") or children[index].get("success_message") or children[index].get("failure_message") or ""),
            }

        if current_active_node_path and any(
            current_active_node_path == f"{path}.children[{index}]"
            or current_active_node_path.startswith(f"{path}.children[{index}].")
            for index in range(len(children))
        ):
            status = "pending"
        elif node_type == "sequence":
            first_progress_index = next((index for index, item in enumerate(child_statuses) if item in {"pending", "success", "failed"}), None)
            if first_progress_index is not None:
                for index in range(first_progress_index):
                    if child_statuses[index] == "unstarted":
                        set_child_status(index, "success")
            if any(item == "failed" for item in child_statuses):
                first_failed = next(index for index, item in enumerate(child_statuses) if item == "failed")
                for index in range(first_failed + 1, len(children)):
                    mark_skipped(children[index], f"{path}.children[{index}]")
                status = "failed"
            elif any(item == "pending" for item in child_statuses):
                status = "pending"
            elif all(item == "success" for item in child_statuses):
                status = "success"
            elif any(item == "success" for item in child_statuses):
                status = "pending"
            else:
                status = "unstarted"
        elif node_type == "selector":
            first_progress_index = next((index for index, item in enumerate(child_statuses) if item in {"pending", "success", "failed"}), None)
            if first_progress_index is not None:
                for index in range(first_progress_index):
                    if child_statuses[index] == "unstarted":
                        set_child_status(index, "failed")
            if any(item == "success" for item in child_statuses):
                first_success = next(index for index, item in enumerate(child_statuses) if item == "success")
                for index in range(first_success + 1, len(children)):
                    mark_skipped(children[index], f"{path}.children[{index}]")
                status = "success"
            elif any(item == "pending" for item in child_statuses):
                status = "pending"
            elif all(item == "failed" for item in child_statuses):
                status = "failed"
            elif any(item == "failed" for item in child_statuses):
                status = "pending"
            else:
                status = "unstarted"
        else:
            if any(item == "failed" for item in child_statuses):
                status = "failed"
            elif any(item == "pending" for item in child_statuses):
                status = "pending"
            elif all(item == "success" for item in child_statuses):
                status = "success"
            elif any(item == "success" for item in child_statuses):
                status = "pending"
            else:
                status = "unstarted"

        node_statuses[path] = {
            "status": status,
            "message": normalize_message_content(node.get("message") or node.get("success_message") or node.get("failure_message") or ""),
        }
        return status

    root_status = walk(root, "root") if isinstance(root, dict) else ("pending" if current_active_node_path else ("success" if script_passed else "failed"))

    return {
        "overall_status": root_status,
        "active_node_path": current_active_node_path,
        "node_statuses": node_statuses,
        "conclusion": final_conclusion,
    }


def clear_live_playbook_state(*, session_id: str = "") -> None:
    """清空当前的 playbook 执行状态，通常在执行完成后调用，或者在需要强制重置状态时调用。"""
    with _state_lock:
        live_state, live_events = _ensure_session_bucket(session_id)
        live_state["playbook"] = None
        live_state["playbook_execution"] = None
        live_state["pending_confirmation"] = None
        live_state["updated_at"] = _now()
        live_state["version"] = int(live_state.get("version") or 0) + 1
        live_events.clear()
        live_events.append(
            {
                "version": live_state["version"],
                "updated_at": live_state["updated_at"],
                "playbook": None,
                "playbook_execution": None,
                "pending_confirmation": None,
            }
        )
        _state_changed.notify_all()


def reset_live_playbook_execution(*, session_id: str = "", playbook: dict[str, Any] | None = None) -> None:
    """重置当前的 playbook 执行状态，通常在开始新的 playbook 执行时调用。可以选择性地提供一个新的 playbook 来替换当前状态中的 playbook。"""
    with _state_lock:
        live_state, live_events = _ensure_session_bucket(session_id)
        if playbook is not None:
            live_state["playbook"] = _clone_payload(playbook)
        live_state["playbook_execution"] = None
        live_state["pending_confirmation"] = None
        live_state["updated_at"] = _now()
        live_state["version"] = int(live_state.get("version") or 0) + 1
        live_events.append(
            {
                "version": live_state["version"],
                "updated_at": live_state["updated_at"],
                "playbook": _clone_payload(live_state.get("playbook")),
                "playbook_execution": None,
                "pending_confirmation": None,
            }
        )
        _state_changed.notify_all()


def publish_live_playbook_state(
    *,
    session_id: str = "",
    playbook: dict[str, Any] | None = None,
    scripted_playbook: dict[str, Any] | None = None,
    pending_confirmation: dict[str, Any] | None = None,
    active_node_path: str = "",
    active_node_message: str = "",
) -> None:
    with _state_lock:
        live_state, live_events = _ensure_session_bucket(session_id)
        live_state["playbook"] = _clone_payload(playbook)
        live_state["playbook_execution"] = build_playbook_execution_payload(
            scripted_playbook,
            pending_confirmation=pending_confirmation,
            active_node_path=active_node_path,
            active_node_message=active_node_message,
        )
        live_state["pending_confirmation"] = _clone_payload(pending_confirmation) if isinstance(pending_confirmation, dict) else None
        live_state["updated_at"] = _now()
        live_state["version"] = int(live_state.get("version") or 0) + 1
        live_events.append(
            {
                "version": live_state["version"],
                "updated_at": live_state["updated_at"],
                "playbook": _clone_payload(live_state["playbook"]),
                "playbook_execution": _clone_payload(live_state["playbook_execution"]),
                "pending_confirmation": _clone_payload(live_state["pending_confirmation"]),
            }
        )
        execution = live_state["playbook_execution"] if isinstance(live_state["playbook_execution"], dict) else {}
        node_statuses = execution.get("node_statuses") if isinstance(execution.get("node_statuses"), dict) else {}
        status_summary = {
            path: normalize_message_content((payload or {}).get("status", ""))
            for path, payload in node_statuses.items()
            if isinstance(payload, dict) and normalize_message_content((payload or {}).get("status", ""))
        }
        logger.info(
            "发布流程图状态 | session_id=%s | version=%s | playbook=%s | overall=%s | active=%s | node_statuses=%s",
            _normalize_session_key(session_id),
            live_state["version"],
            normalize_message_content((playbook or {}).get("id", "")),
            normalize_message_content(execution.get("overall_status", "")),
            normalize_message_content(execution.get("active_node_path", "")),
            json.dumps(status_summary, ensure_ascii=False),
        )
        _state_changed.notify_all()


def get_live_playbook_state(*, session_id: str = "", since_version: int = 0) -> dict[str, Any]:
    with _state_lock:
        live_state, live_events = _ensure_session_bucket(session_id)
        latest_version = int(live_state.get("version") or 0)
        events = [
            _clone_payload(event)
            for event in live_events
            if int(event.get("version") or 0) > since_version
        ]
        return {
            "playbook": _clone_payload(live_state.get("playbook")),
            "playbook_execution": _clone_payload(live_state.get("playbook_execution")),
            "pending_confirmation": _clone_payload(live_state.get("pending_confirmation")),
            "updated_at": live_state.get("updated_at") or 0.0,
            "version": latest_version,
            "events": events,
        }


def stream_live_playbook_events(
    *,
    session_id: str = "",
    since_version: int = 0,
    heartbeat_seconds: float = 60.0,
) -> Iterator[str]:
    session_key = _normalize_session_key(session_id)
    current_version = max(int(since_version), 0)
    while True:
        payload: dict[str, Any] | None = None
        with _state_changed:
            live_state, _ = _ensure_session_bucket(session_key)
            latest_version = int(live_state.get("version") or 0)
            if latest_version <= current_version:
                _state_changed.wait(timeout=heartbeat_seconds)
                live_state, _ = _ensure_session_bucket(session_key)
                latest_version = int(live_state.get("version") or 0)
            if latest_version > current_version:
                payload = get_live_playbook_state(session_id=session_key, since_version=current_version)
                current_version = int(payload.get("version") or current_version)
        if payload is not None:
            yield "event: playbook_state\n"
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            continue
        yield "event: heartbeat\n"
        yield "data: {}\n\n"
