from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.runtime.operations.services import current_robot_password
from backend.runtime.workflow.confirmation import get_runtime_value, set_context_value, set_runtime_value
from ..base import ToolRuntime, with_target_tool_runtime
from ..remote import DeviceTypeArgs
from .impl import (
    prepare_artifact_sources,
    remote_execute_with_fallback,
    remote_stage_artifacts,
)

class PrepareArtifactSourcesArgs(BaseModel):
    source_items: list[dict[str, Any]] = Field(default_factory=list)
    upload_token: str = ""


class RemoteStageArtifactsArgs(DeviceTypeArgs):
    target_root: str
    target_mode: str = "directory"
    artifact_items: list[dict[str, Any]] = Field(default_factory=list)
    upload_token: str = ""


class RemoteExecuteWithFallbackArgs(DeviceTypeArgs):
    command_template: str
    command_args: dict[str, Any] = Field(default_factory=dict)
    parse_mode: str = "command_result"
    on_failure: str = "raise"
    fallback_value: Any = None
    timeout_seconds: int = 30
    target_credentials_probe: dict[str, Any] | None = None
def handle_prepare_artifact_sources(args: PrepareArtifactSourcesArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    normalized_upload_token = str(args.upload_token or get_runtime_value(tool_context, "upload_token") or "").strip()
    result = prepare_artifact_sources(list(args.source_items or []), upload_token=normalized_upload_token)
    if isinstance(tool_context, dict):
        artifact_items = list(result.get("artifact_items") or [])
        set_runtime_value(tool_context, "artifact_items", artifact_items)
        set_runtime_value(tool_context, "package_files", list(result.get("package_files") or []))
        if artifact_items:
            first_item = artifact_items[0] if isinstance(artifact_items[0], dict) else {}
            set_runtime_value(tool_context, "file_name", str(first_item.get("file_name") or "").strip())
            set_runtime_value(tool_context, "file_size", int(first_item.get("file_size") or 0))
            set_runtime_value(tool_context, "local_tmp_path", str(first_item.get("local_tmp_path") or "").strip())
            if isinstance(first_item.get("source_metadata"), dict):
                set_context_value(tool_context, "source_metadata", first_item.get("source_metadata"))
    return {
        "artifact_count": int(result.get("artifact_count") or 0),
        "total_bytes": int(result.get("total_bytes") or 0),
        "file_names": list(result.get("file_names") or []),
        "file_name": str(result.get("file_name") or "").strip(),
        "file_size": int(result.get("file_size") or 0),
        "source_metadata": result.get("source_metadata") or {},
        "source_kind": str(result.get("source_kind") or "").strip(),
        "download_path": str(result.get("download_path") or "").strip(),
        "local_tmp_path": str(result.get("local_tmp_path") or "").strip(),
    }


def handle_remote_stage_artifacts(args: RemoteStageArtifactsArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    artifact_items = list(args.artifact_items or [])
    upload_token = str(args.upload_token or get_runtime_value(tool_context, "upload_token") or "").strip()

    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, object]:
        try:
            result = remote_stage_artifacts(
                runtime.client,
                target_root=args.target_root,
                target_mode=str(args.target_mode or ""),
                artifact_items=artifact_items,
                upload_token=upload_token,
                sudo_password=current_robot_password(runtime.session),
            )
        except Exception as exc:  # noqa: BLE001
            if upload_token:
                from backend.infra.container import upload_progress_manager

                upload_progress_manager.fail(upload_token, f"上传失败: {exc}")
            raise
        if isinstance(tool_context, dict):
            set_runtime_value(tool_context, "uploaded_file_paths", result.get("uploaded_file_paths") or [])
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_remote_execute_with_fallback(args: RemoteExecuteWithFallbackArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, object]:
        result = remote_execute_with_fallback(
            runtime.client,
            command_template=str(args.command_template or ""),
            command_args=dict(args.command_args or {}),
            parse_mode=str(args.parse_mode or ""),
            on_failure=str(args.on_failure or ""),
            fallback_value=args.fallback_value,
            timeout_seconds=int(args.timeout_seconds or 0),
            device_type=str(target.get("device_type") or args.device_type).upper(),
            target_username=str(target.get("username") or ""),
            target_password=str(target.get("password") or ""),
            target_credentials_probe=dict(args.target_credentials_probe or {}),
            output_callback=get_runtime_value(tool_context, "install_output_callback"),
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)
