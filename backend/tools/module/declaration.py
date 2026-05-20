from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ...core.models import ApiError
from ...operations.services import current_robot_password
from ..base import ToolRuntime, connected_tool
from .impl import (
    module_health_check,
    module_install,
    module_prepare_packages,
    module_replace_remote_assets,
    module_stage_packages,
    module_start,
)


class ModulePreparePackagesArgs(BaseModel):
    pass


class ModuleReplaceRemoteAssetsArgs(BaseModel):
    module_name: str
    auto_deploy: bool = False
    auto_deploy_version: str = ""


class ModuleStagePackagesArgs(BaseModel):
    module_name: str
    module_path: str
    auto_deploy: bool = False


class ModuleInstallArgs(BaseModel):
    module_name: str
    module_path: str
    install_template: str


class ModuleStartArgs(BaseModel):
    module_name: str
    module_path: str
    start_command: str = ""
    up_wait_seconds: int = 0


class ModuleHealthCheckArgs(BaseModel):
    module_name: str
    module_path: str
    health_command: str = ""
    rollback_template: str = ""
    auto_rollback: bool = False


@connected_tool
def handle_module_prepare_packages(args: ModulePreparePackagesArgs, runtime: ToolRuntime) -> dict[str, Any]:
    package_sources = (runtime.tool_context or {}).get("package_sources")
    if not isinstance(package_sources, list) or not package_sources:
        raise ApiError("模块部署上下文缺少安装包来源列表")
    upload_token = str((runtime.tool_context or {}).get("upload_token") or "").strip()
    result = module_prepare_packages(package_sources, upload_token=upload_token)
    if isinstance(runtime.tool_context, dict):
        runtime.tool_context["package_files"] = result.get("package_files")
    return {
        "package_count": int(result.get("package_count") or 0),
        "total_bytes": int(result.get("total_bytes") or 0),
        "package_file_names": list(result.get("package_file_names") or []),
    }


@connected_tool
def handle_module_replace_remote_assets(args: ModuleReplaceRemoteAssetsArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return module_replace_remote_assets(
        runtime.client,
        module_name=args.module_name,
        auto_deploy=bool(args.auto_deploy),
        auto_deploy_version=str(args.auto_deploy_version or "").strip(),
        sudo_password=current_robot_password(runtime.session),
    )


@connected_tool
def handle_module_stage_packages(args: ModuleStagePackagesArgs, runtime: ToolRuntime) -> dict[str, Any]:
    package_files = (runtime.tool_context or {}).get("package_files")
    if not isinstance(package_files, list) or not package_files:
        raise ApiError("模块部署上下文缺少已准备的安装包列表")
    upload_token = str((runtime.tool_context or {}).get("upload_token") or "").strip()
    result = module_stage_packages(
        runtime.client,
        module_name=args.module_name,
        module_path=args.module_path,
        package_files=package_files,
        auto_deploy=bool(args.auto_deploy),
        upload_token=upload_token,
        sudo_password=current_robot_password(runtime.session),
    )
    if isinstance(runtime.tool_context, dict):
        runtime.tool_context["uploaded_file_paths"] = result.get("uploaded_file_paths") or []
    return result


@connected_tool
def handle_module_install(args: ModuleInstallArgs, runtime: ToolRuntime) -> dict[str, Any]:
    uploaded_file_paths = (runtime.tool_context or {}).get("uploaded_file_paths")
    if not isinstance(uploaded_file_paths, list):
        raise ApiError("模块部署上下文缺少上传结果")
    result = module_install(
        runtime.client,
        module_name=args.module_name,
        module_path=args.module_path,
        install_template=str(args.install_template or ""),
        uploaded_file_paths=uploaded_file_paths,
    )
    if isinstance(runtime.tool_context, dict):
        runtime.tool_context["compose_profiles"] = str(result.get("compose_profiles") or "")
        runtime.tool_context["install_command"] = str(result.get("install_command") or "")
    return result


@connected_tool
def handle_module_start(args: ModuleStartArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return module_start(
        runtime.client,
        module_name=args.module_name,
        module_path=args.module_path,
        start_command=str(args.start_command or ""),
        up_wait_seconds=int(args.up_wait_seconds or 0),
    )


@connected_tool
def handle_module_health_check(args: ModuleHealthCheckArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return module_health_check(
        runtime.client,
        module_name=args.module_name,
        module_path=args.module_path,
        health_command=str(args.health_command or ""),
        rollback_template=str(args.rollback_template or ""),
        auto_rollback=bool(args.auto_rollback),
    )
