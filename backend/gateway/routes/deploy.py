import posixpath

from fastapi import APIRouter, File, Form, Request, UploadFile

from ...core.config import DEPLOY_CONFIG_PATH, MODULE_DEPLOY_ROOT
from ...core.models import ApiError
from ...runtime.operations.services import ensure_client_connected
from ...runtime.operations.workflow import (
    create_module_workflow_task_runner,
    create_package_target_client,
    create_package_workflow_task_runner,
    resolve_deploy_target,
)
from ...core.files import prepare_package_source
from ...core.validation import require_text
from ...infra.container import deploy_config_store, task_manager
from ..support import get_session, get_session_id

router = APIRouter()


@router.get("/api/deploy-target")
def api_deploy_target(request: Request, file_name: str = "", machine_type: str = "", device_type: str = "ORIN"):
    session = get_session(request)
    client, should_close_target_client, _ = create_package_target_client(session, device_type)
    try:
        resolved_remote_dir, normalized_file_name, remote_path = resolve_deploy_target(client, file_name)
        return {
            "ok": True,
            "remote_dir": resolved_remote_dir,
            "file_name": normalized_file_name,
            "remote_path": remote_path,
            "exists": client.path_exists(remote_path),
        }
    finally:
        if should_close_target_client:
            client.close()


@router.post("/api/deploy")
def api_deploy(
    request: Request,
    machine_type: str = Form(""),
    device_type: str = Form("ORIN"),
    server_file_path: str = Form(""),
    upload_token: str = Form(""),
    deb_file: UploadFile | None = File(None),
):
    session = get_session(request)
    session_id = get_session_id(request)
    client, should_close_target_client, target = create_package_target_client(session, device_type)
    try:
        selected_file_name, source_metadata = prepare_package_source(
            deb_file,
            server_file_path,
            local_error_message="请选择要部署的安装包文件或填写文件服务器包路径",
        )
        resolved_remote_dir, selected_file_name, remote_path = resolve_deploy_target(client, selected_file_name)
        deploy_profile = deploy_config_store.get_profile("package", machine_type, auto_select_default=bool(str(machine_type or "").strip()))
        title, metadata, runner = create_package_workflow_task_runner(
            session,
            remote_dir=resolved_remote_dir,
            machine_type=str(deploy_profile.get("machine_type") or ""),
            device_type=str(target.get("device_type") or device_type).upper(),
            rollback_template=deploy_profile["rollback_template"],
            file_name=selected_file_name,
            source_metadata=source_metadata,
            upload_token=str(upload_token or "").strip(),
            owner_id=session_id,
        )
        metadata.update(
            {
                "deploy_mode": "package",
                "remote_dir": resolved_remote_dir,
                "remote_path": remote_path,
                "deploy_config_path": str(DEPLOY_CONFIG_PATH),
                "machine_type": str(deploy_profile.get("machine_type") or ""),
                "device_type": str(target.get("device_type") or device_type).upper(),
                "target_host": str(target.get("host") or ""),
                "target_port": int(target.get("port") or 22),
                "target_username": str(target.get("username") or ""),
                "source_kind": str(source_metadata.get("source_kind") or ""),
                "source_path": str(source_metadata.get("source_path") or ""),
                "download_path": str(source_metadata.get("download_path") or ""),
            }
        )
        return {"ok": True, "task": task_manager.create_task("deployment", title, metadata, runner, owner_id=session_id)}
    finally:
        if should_close_target_client:
            client.close()


@router.post("/api/deploy-module")
def api_deploy_module(
    request: Request,
    module_name: str = Form(""),
    server_file_path: str = Form(""),
    upload_token: str = Form(""),
    deb_file: UploadFile | None = File(None),
):
    session = get_session(request)
    session_id = get_session_id(request)
    client = ensure_client_connected(session)
    selected_module_name = require_text(module_name, "请选择要部署的模块")
    selected_module_path = client.resolve_remote_path(posixpath.join(MODULE_DEPLOY_ROOT, selected_module_name))
    if not client.path_exists(selected_module_path):
        raise ApiError(f"模块目录不存在: {selected_module_path}")
    if not client.is_dir_path(selected_module_path):
        raise ApiError(f"模块路径不是目录: {selected_module_path}")
    package_file_name, source_metadata = prepare_package_source(
        deb_file,
        server_file_path,
        local_error_message="请选择要部署的模块 deb 文件或填写文件服务器包路径",
    )
    package_sources = [{"package_file_name": package_file_name, "source_metadata": source_metadata}]
    title, metadata, runner = create_module_workflow_task_runner(
        session,
        module_name=selected_module_name,
        module_path=selected_module_path,
        package_sources=package_sources,
        upload_token=str(upload_token or "").strip(),
        owner_id=session_id,
    )
    first_package_name = str(package_sources[0].get("package_file_name") or "")
    first_source_metadata = package_sources[0].get("source_metadata") if isinstance(package_sources[0].get("source_metadata"), dict) else {}
    metadata.update(
        {
            "deploy_mode": "module",
            "module_name": selected_module_name,
            "module_path": selected_module_path,
            "package_file_name": first_package_name,
            "package_file_names": [str(item.get("package_file_name") or "") for item in package_sources],
            "package_count": len(package_sources),
            "package_prefix": first_package_name.split("_", 1)[0].strip() if first_package_name else "",
            "remote_path": client.resolve_remote_path(posixpath.join(selected_module_path, first_package_name)) if first_package_name else selected_module_path,
            "remote_paths": [
                client.resolve_remote_path(posixpath.join(selected_module_path, str(item.get("package_file_name") or "")))
                for item in package_sources
                if str(item.get("package_file_name") or "").strip()
            ],
            "deploy_config_path": str(DEPLOY_CONFIG_PATH),
            "source_kind": str(first_source_metadata.get("source_kind") or ""),
            "source_path": str(first_source_metadata.get("source_path") or ""),
            "download_path": str(first_source_metadata.get("download_path") or ""),
        }
    )
    return {"ok": True, "task": task_manager.create_task("deployment", title, metadata, runner, owner_id=session_id)}
