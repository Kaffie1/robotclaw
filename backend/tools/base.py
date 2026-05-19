from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from pydantic import BaseModel

from ..core.models import ApiError
from ..shared.runtime import session_store
from ..operations.deploy import create_package_target_client
from ..operations.services import ensure_client_connected


@dataclass(frozen=True)
class ToolRuntime:
    session: dict[str, Any]
    client: Any
    tool_context: dict[str, Any] | None


@dataclass
class ToolDefinition:
    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[[BaseModel, dict[str, Any] | None], dict[str, Any]]
    module: str = ""
    aliases: tuple[str, ...] = ()


def ensure_tool_session(tool_context: dict[str, Any] | None) -> dict[str, Any]:
    session = (tool_context or {}).get("session")
    if isinstance(session, dict):
        return session
    session_id = str((tool_context or {}).get("session_id") or "").strip()
    resolved_session = session_store.get(session_id)
    if not isinstance(resolved_session, dict):
        raise ApiError("当前工具调用缺少会话上下文")
    return resolved_session


def build_tool_runtime(tool_context: dict[str, Any] | None) -> ToolRuntime:
    session = ensure_tool_session(tool_context)
    client = ensure_client_connected(session)
    return ToolRuntime(session=session, client=client, tool_context=tool_context)


def _normalize_device_type(device_type: str) -> str:
    normalized_device_type = str(device_type or "ORIN").strip().upper() or "ORIN"
    if normalized_device_type not in {"ORIN", "PICO"}:
        raise ApiError(f"不支持的设备类型: {normalized_device_type}")
    return normalized_device_type


def with_target_tool_runtime(
    tool_context: dict[str, Any] | None,
    *,
    device_type: str,
    handler: Callable[[ToolRuntime, dict[str, Any], bool], dict[str, Any]],
) -> dict[str, Any]:
    session = ensure_tool_session(tool_context)
    client, should_close_target_client, target = create_package_target_client(
        session,
        _normalize_device_type(device_type),
    )
    runtime = ToolRuntime(session=session, client=client, tool_context=tool_context)
    try:
        return handler(runtime, target, should_close_target_client)
    finally:
        if should_close_target_client:
            client.close()


def connected_tool(handler: Callable[[BaseModel, ToolRuntime], dict[str, Any]]) -> Callable[[BaseModel, dict[str, Any] | None], dict[str, Any]]:
    @wraps(handler)
    def wrapper(args: BaseModel, tool_context: dict[str, Any] | None) -> dict[str, Any]:
        runtime = build_tool_runtime(tool_context)
        return handler(args, runtime)

    return wrapper
