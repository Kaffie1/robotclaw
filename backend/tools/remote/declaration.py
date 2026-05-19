from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ...core.models import ApiError
from ..base import ToolRuntime, with_target_tool_runtime
from .impl import (
    ping_host,
    remote_backup_path,
    remote_ensure_executable,
    remote_execute_command,
    remote_execute_readonly,
    remote_get_file_owner,
    remote_get_interactive_env,
    remote_list_dir,
    remote_path_exists,
    remote_read_file,
    remote_remove_files_by_prefix,
    remote_resolve_path,
    remote_restore_backup,
    remote_scan_paths,
    remote_shortcuts,
)


class DeviceTypeArgs(BaseModel):
    device_type: str = "ORIN"


class RemotePathArgs(DeviceTypeArgs):
    path: str = "/"


class RemoteScanPathsArgs(DeviceTypeArgs):
    root: str = "/"
    keyword: str = ""


class RemoteExecuteArgs(DeviceTypeArgs):
    command: str
    interactive: bool = False
    timeout_seconds: int = 30


class RemoteCommandArgs(DeviceTypeArgs):
    command: str
    interactive: bool = False
    timeout_seconds: int = 30


class PingHostArgs(BaseModel):
    host: str
    count: int = 1
    timeout_seconds: int = 2


class RemoteEnvironmentVariableArgs(DeviceTypeArgs):
    name: str = Field(default="")
    timeout_seconds: int = 10

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_path_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if not data.get("name") and data.get("path"):
            upgraded = dict(data)
            upgraded["name"] = upgraded.get("path")
            return upgraded
        return data


class RemotePathPrefixArgs(DeviceTypeArgs):
    remote_dir: str
    prefix: str


class RemoteFileTransferArgs(DeviceTypeArgs):
    path: str
    backup_path: str = ""


RemoteMutableExecuteArgs = RemoteCommandArgs
RemotePathWithTimeoutArgs = RemoteEnvironmentVariableArgs


def handle_ping_host(args: PingHostArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = ping_host(runtime.client, args.host, count=args.count, timeout_seconds=args.timeout_seconds)
        return {**result, "device_type": str(target.get("device_type") or "ORIN").upper()}

    return with_target_tool_runtime(tool_context, device_type="ORIN", handler=_handler)


def handle_remote_resolve_path(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_resolve_path(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_path_exists(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_path_exists(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_list_dir(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_list_dir(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_scan_paths(args: RemoteScanPathsArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_scan_paths(runtime.client, args.root, args.keyword, runtime.session)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_shortcuts(args: DeviceTypeArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], should_close_target_client: bool) -> dict[str, Any]:
        result = remote_shortcuts(
            runtime.client,
            should_cache=(not should_close_target_client and str(target.get("device_type") or args.device_type).upper() == "ORIN"),
            session=runtime.session,
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_execute_readonly(args: RemoteExecuteArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_execute_readonly(
            runtime.client,
            args.command,
            interactive=args.interactive,
            timeout_seconds=args.timeout_seconds,
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_execute_command(args: RemoteCommandArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_execute_command(
            runtime.client,
            args.command,
            interactive=args.interactive,
            timeout_seconds=args.timeout_seconds,
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_get_interactive_env(args: RemoteEnvironmentVariableArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_get_interactive_env(runtime.client, args.name, timeout_seconds=args.timeout_seconds)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_ensure_executable(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_ensure_executable(runtime.client, args.path, sudo_password=str(target.get("password") or ""))
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_read_file(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_read_file(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_get_file_owner(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_get_file_owner(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_backup_path(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_backup_path(runtime.client, args.path, sudo_password=str(target.get("password") or ""))
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_restore_backup(args: RemoteFileTransferArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_restore_backup(runtime.client, args.path, args.backup_path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_remove_files_by_prefix(args: RemotePathPrefixArgs, tool_context: dict[str, Any] | None) -> dict[str, Any]:
    def _handler(runtime: ToolRuntime, target: dict[str, Any], _: bool) -> dict[str, Any]:
        result = remote_remove_files_by_prefix(
            runtime.client,
            args.remote_dir,
            args.prefix,
            sudo_password=str(target.get("password") or ""),
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)
