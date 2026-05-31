from __future__ import annotations

import copy
import threading
from typing import Any

_lock = threading.RLock()
_thread_tool_contexts: dict[str, dict[str, Any]] = {}


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(item)
            for key, item in value.items()
            if key != "session"
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    return str(value)


def _clone_context(value: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(_sanitize_value(value or {}))


def sanitize_tool_context(tool_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tool_context, dict):
        return {}
    return _clone_context(tool_context)


def store_runtime_tool_context(thread_id: str, tool_context: dict[str, Any] | None) -> None:
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    with _lock:
        _thread_tool_contexts[normalized_thread_id] = _clone_context(tool_context)


def get_runtime_tool_context(thread_id: str) -> dict[str, Any]:
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return {}
    with _lock:
        return _clone_context(_thread_tool_contexts.get(normalized_thread_id))


def hydrate_runtime_tool_context(thread_id: str, state_context: dict[str, Any] | None) -> dict[str, Any]:
    runtime_context = get_runtime_tool_context(thread_id)
    runtime_context.update(_clone_context(state_context))
    return runtime_context


def clear_runtime_tool_context(thread_id: str) -> None:
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    with _lock:
        _thread_tool_contexts.pop(normalized_thread_id, None)


def clear_runtime_tool_contexts_for_session(session_id: str) -> int:
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        return 0
    removed_count = 0
    with _lock:
        stale_thread_ids = [
            thread_id
            for thread_id, tool_context in _thread_tool_contexts.items()
            if str((tool_context or {}).get("session_id") or "").strip() == normalized_session_id
        ]
        for thread_id in stale_thread_ids:
            _thread_tool_contexts.pop(thread_id, None)
            removed_count += 1
    return removed_count
