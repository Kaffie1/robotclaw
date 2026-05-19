from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ...core.models import ApiError
from ..base import ToolRuntime, with_target_tool_runtime
from ..remote import DeviceTypeArgs, RemotePathArgs
from .impl import package_install, package_prepare_source, package_probe_credentials, package_probe_machine_types, package_stage_remote


class PackagePrepareSourceArgs(BaseModel):
    pass


class PackageInstallArgs(DeviceTypeArgs):
    deb_path: str
    machine_type: str = ""
    install_template: str = "chmod +x {deb_path} && {deb_path} -- --force --robot_type={machine_type} --user={target_username} --password={target_password}"
    timeout_seconds: int = 1800


class PackageStageRemoteArgs(DeviceTypeArgs):
    remote_deb_path: str
    file_name: str
    cleanup_existing_remote_files: bool = True


class PackageProbeMachineTypesArgs(DeviceTypeArgs):
    deb_path: str
    probe_command_template: str = "chmod +x {deb_path} && {deb_path} --quiet -- support_robot_types"
    fallback_machine_options: list[dict[str, str]] = []


def handle_package_probe_credentials(args: RemotePathArgs, tool_context: dict[str, Any] | None) -> dict[str, str | bool]:
    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, str | bool]:
        result = package_probe_credentials(runtime.client, args.path)
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_package_prepare_source(args: PackagePrepareSourceArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    source_metadata = (tool_context or {}).get("source_metadata")
    if not isinstance(source_metadata, dict):
        raise ApiError("部署 workflow 缺少安装包来源信息")
    upload_token = str((tool_context or {}).get("upload_token") or "").strip()
    result = package_prepare_source(source_metadata, upload_token=upload_token)
    if isinstance(tool_context, dict):
        tool_context["file_name"] = str(result.get("file_name") or "").strip()
        tool_context["source_metadata"] = result.get("source_metadata") if isinstance(result.get("source_metadata"), dict) else source_metadata
        tool_context["file_bytes"] = bytes(result.get("_file_bytes") or b"")
    return {
        "file_name": str(result.get("file_name") or "").strip(),
        "source_metadata": result.get("source_metadata"),
        "file_size": int(result.get("file_size") or 0),
        "source_kind": str(result.get("source_kind") or "").strip(),
        "download_path": str(result.get("download_path") or "").strip(),
        "local_tmp_path": str(result.get("local_tmp_path") or "").strip(),
    }


def handle_package_install(args: PackageInstallArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, object]:
        result = package_install(
            runtime.client,
            args.deb_path,
            machine_type=args.machine_type,
            install_template=str(args.install_template or ""),
            timeout_seconds=args.timeout_seconds,
            device_type=str(target.get("device_type") or args.device_type),
            target_username=str(target.get("username") or ""),
            target_password=str(target.get("password") or ""),
            output_callback=(tool_context or {}).get("install_output_callback"),
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_package_stage_remote(args: PackageStageRemoteArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    file_bytes = (tool_context or {}).get("file_bytes")
    if not isinstance(file_bytes, (bytes, bytearray)):
        raise ApiError("部署 workflow 缺少待上传安装包内容")
    upload_token = str((tool_context or {}).get("upload_token") or "").strip()

    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, object]:
        try:
            result = package_stage_remote(
                runtime.client,
                args.remote_deb_path,
                file_name=args.file_name,
                file_bytes=bytes(file_bytes or b""),
                cleanup_existing_remote_files=args.cleanup_existing_remote_files,
                upload_token=upload_token,
            )
        except Exception as exc:  # noqa: BLE001
            if upload_token:
                from ...shared.runtime import upload_progress_manager

                upload_progress_manager.fail(upload_token, f"上传失败: {exc}")
            raise
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)


def handle_package_probe_machine_types(args: PackageProbeMachineTypesArgs, tool_context: dict[str, Any] | None) -> dict[str, object]:
    def _handler(runtime: ToolRuntime, target: dict[str, str], _: bool) -> dict[str, object]:
        result = package_probe_machine_types(
            runtime.client,
            args.deb_path,
            probe_command_template=str(args.probe_command_template or ""),
            fallback_machine_options=list(args.fallback_machine_options or []),
        )
        return {**result, "device_type": str(target.get("device_type") or args.device_type).upper()}

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)
