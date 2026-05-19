from __future__ import annotations

import posixpath
import tempfile
import time
from pathlib import Path
from typing import Any

from ...common import extract_package_prefix, log_command_result, render_remote_command
from ...core.config import LOCAL_MODULE_DIR, MODULE_DEPLOY_PROJECT_ROOT, PACKAGE_DEPLOY_DIR
from ...core.models import ApiError
from ...shared.files import materialize_package_bytes_from_source
from ...shared.runtime import upload_progress_manager


def _extract_compose_service_block(compose_text: str, service_name: str) -> str:
    lines = str(compose_text or "").splitlines()
    in_services = False
    service_start = -1
    service_end = -1
    target_prefix = f"  {service_name}:"
    for index, line in enumerate(lines):
        if not in_services:
            if line.strip() == "services:":
                in_services = True
            continue
        if line and not line.startswith(" "):
            break
        if service_start < 0:
            if line.startswith(target_prefix):
                service_start = index
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            service_end = index
            break
    if service_start < 0:
        raise ApiError(f"版本 docker-compose.yaml 中未找到模块服务: {service_name}")
    if service_end < 0:
        service_end = len(lines)
    return "\n".join(lines[service_start:service_end]).rstrip() + "\n"


def _merge_compose_service_block(current_text: str, service_name: str, replacement_block: str) -> str:
    lines = str(current_text or "").splitlines()
    if not lines:
        raise ApiError("远端 docker-compose.yaml 为空，无法替换模块片段")
    in_services = False
    services_line = -1
    service_start = -1
    service_end = -1
    target_prefix = f"  {service_name}:"
    for index, line in enumerate(lines):
        if not in_services:
            if line.strip() == "services:":
                in_services = True
                services_line = index
            continue
        if line and not line.startswith(" "):
            if service_start >= 0 and service_end < 0:
                service_end = index
            break
        if service_start < 0:
            if line.startswith(target_prefix):
                service_start = index
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            service_end = index
            break
    if services_line < 0:
        raise ApiError("远端 docker-compose.yaml 缺少 services 段")
    replacement_lines = replacement_block.rstrip("\n").splitlines()
    if service_start >= 0:
        if service_end < 0:
            service_end = len(lines)
        merged_lines = [*lines[:service_start], *replacement_lines, *lines[service_end:]]
        return "\n".join(merged_lines).rstrip() + "\n"
    insert_at = len(lines)
    for index in range(services_line + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith(" "):
            insert_at = index
            break
    merged_lines = [*lines[:insert_at], *replacement_lines, *lines[insert_at:]]
    return "\n".join(merged_lines).rstrip() + "\n"


def _resolve_local_module_assets(module_name: str, version: str) -> dict[str, Path]:
    normalized_version = str(version or "").strip()
    if not normalized_version:
        raise ApiError("自动模块部署缺少版本号")
    version_dir = LOCAL_MODULE_DIR / normalized_version
    if not version_dir.exists() or not version_dir.is_dir():
        raise ApiError(f"本地模块版本目录不存在: {version_dir}")
    module_dir_name = module_name.strip().lower()
    config_dir = version_dir / "config" / module_dir_name
    containers_dir = version_dir / "containers" / module_dir_name
    compose_file = version_dir / "docker-compose.yaml"
    if not compose_file.exists() or not compose_file.is_file():
        raise ApiError(f"版本目录缺少 docker-compose.yaml: {compose_file}")
    if not config_dir.exists() and not containers_dir.exists():
        raise ApiError(f"版本目录中未找到模块 {module_dir_name} 的 config 或 containers 资源")
    return {
        "version_dir": version_dir,
        "config_dir": config_dir,
        "containers_dir": containers_dir,
        "compose_file": compose_file,
        "module_dir_name": Path(module_dir_name),
    }


def module_prepare_packages(
    package_sources: list[dict[str, Any]],
    *,
    upload_token: str,
) -> dict[str, Any]:
    if not isinstance(package_sources, list) or not package_sources:
        raise ApiError("模块部署缺少安装包来源")
    prepared_packages: list[dict[str, Any]] = []
    total_bytes = 0
    total_count = len(package_sources)
    for index, source in enumerate(package_sources, start=1):
        source_metadata = source.get("source_metadata") if isinstance(source, dict) else None
        if not isinstance(source_metadata, dict):
            raise ApiError("模块部署安装包来源格式错误")
        source_kind = str(source_metadata.get("source_kind") or "").strip()
        if source_kind == "file_server":
            upload_progress_manager.update(
                upload_token,
                phase="downloading_from_server",
                message=f"[{index}/{total_count}] 正在从文件服务器下载: {source_metadata.get('download_path') or source_metadata.get('source_path')}",
            )
        else:
            upload_progress_manager.update(
                upload_token,
                phase="preparing",
                message=f"[{index}/{total_count}] 正在准备本地上传的模块安装包",
            )
        package_file_name, package_file_bytes, resolved_source_metadata = materialize_package_bytes_from_source(
            source_metadata,
            local_error_message="请选择要部署的模块 deb 文件或填写文件服务器包路径",
        )
        total_bytes += len(package_file_bytes)
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=total_bytes if source_kind == "file_server" else 0,
            total_bytes=total_bytes,
            phase="queued",
            message=f"[{index}/{total_count}] 模块安装包已准备完成: {package_file_name}",
        )
        prepared_packages.append(
            {
                "package_file_name": package_file_name,
                "package_file_bytes": package_file_bytes,
                "source_metadata": resolved_source_metadata,
            }
        )
    return {
        "package_files": prepared_packages,
        "package_count": len(prepared_packages),
        "total_bytes": total_bytes,
        "package_file_names": [str(item.get("package_file_name") or "") for item in prepared_packages],
    }


def module_replace_remote_assets(
    client,
    *,
    module_name: str,
    auto_deploy: bool,
    auto_deploy_version: str,
    sudo_password: str,
) -> dict[str, Any]:
    if not auto_deploy:
        return {
            "auto_deploy": False,
            "replaced_paths": [],
            "local_module_assets": {},
            "auto_deploy_version": "",
            "project_root": "",
            "result": {"exit_code": 0, "stdout": "", "stderr": ""},
        }
    assets = _resolve_local_module_assets(module_name, auto_deploy_version)
    project_root = client.resolve_remote_path(MODULE_DEPLOY_PROJECT_ROOT)
    remote_config_root = client.resolve_remote_path(posixpath.join(project_root, "config"))
    remote_containers_root = client.resolve_remote_path(posixpath.join(project_root, "containers"))
    remote_compose_path = client.resolve_remote_path(posixpath.join(project_root, "docker-compose.yaml"))
    remote_config_target = client.resolve_remote_path(posixpath.join(remote_config_root, str(assets["module_dir_name"])))
    remote_containers_target = client.resolve_remote_path(posixpath.join(remote_containers_root, str(assets["module_dir_name"])))

    if not client.path_exists(project_root) or not client.is_dir_path(project_root):
        raise ApiError(f"机器人项目目录不存在: {project_root}")

    replaced_paths: list[str] = []
    if assets["config_dir"].exists():
        client.remove_remote_path(remote_config_target, recursive=True, sudo_password=sudo_password)
        client.upload_local_tree(assets["config_dir"], remote_config_target)
        replaced_paths.append(remote_config_target)

    if assets["containers_dir"].exists():
        client.remove_remote_path(remote_containers_target, recursive=True, sudo_password=sudo_password)
        client.upload_local_tree(assets["containers_dir"], remote_containers_target)
        replaced_paths.append(remote_containers_target)

    with tempfile.NamedTemporaryFile(prefix="docker-compose-", suffix=".yaml", delete=False) as temp_file:
        temp_local_compose = Path(temp_file.name)
    try:
        local_compose_text = assets["compose_file"].read_text(encoding="utf-8")
        local_service_block = _extract_compose_service_block(local_compose_text, str(assets["module_dir_name"]))
        remote_compose_text = client.read_file_bytes(remote_compose_path).decode("utf-8", errors="replace")
        merged_compose_text = _merge_compose_service_block(remote_compose_text, str(assets["module_dir_name"]), local_service_block)
        temp_local_compose.write_text(merged_compose_text, encoding="utf-8")
        remote_temp_compose = client.resolve_remote_path(posixpath.join(PACKAGE_DEPLOY_DIR, f"docker-compose.{module_name.lower()}.yaml"))
        client.upload_local_file(temp_local_compose, remote_temp_compose)
        client.remove_remote_path(remote_compose_path, sudo_password=sudo_password)
        move_result = client.move_remote_path(remote_temp_compose, remote_compose_path, sudo_password=sudo_password)
        replaced_paths.append(remote_compose_path)
    finally:
        try:
            temp_local_compose.unlink(missing_ok=True)
        except OSError:
            pass
    return {
        "auto_deploy": True,
        "auto_deploy_version": auto_deploy_version,
        "project_root": project_root,
        "replaced_paths": replaced_paths,
        "local_module_assets": {
            "version_dir": str(assets["version_dir"]),
            "config_dir": str(assets["config_dir"]) if assets["config_dir"].exists() else "",
            "containers_dir": str(assets["containers_dir"]) if assets["containers_dir"].exists() else "",
            "compose_file": str(assets["compose_file"]),
        },
        "result": move_result,
    }


def module_stage_packages(
    client,
    *,
    module_name: str,
    module_path: str,
    package_files: list[dict[str, Any]],
    auto_deploy: bool,
    upload_token: str,
    sudo_password: str,
) -> dict[str, Any]:
    total_bytes = sum(len(item.get("package_file_bytes") or b"") for item in package_files)
    transferred_total = 0
    package_summaries: list[dict[str, Any]] = []
    removed_files: list[str] = []
    uploaded_file_paths: list[str] = []
    skipped_existing_files: list[str] = []
    upload_progress_manager.update(
        upload_token,
        total_bytes=total_bytes,
        phase="preparing",
        message="模块部署任务已创建，准备清理旧包",
    )
    for package_index, package_item in enumerate(package_files, start=1):
        package_file_name = str(package_item.get("package_file_name") or "").strip()
        package_file_bytes = bytes(package_item.get("package_file_bytes") or b"")
        source_metadata = package_item.get("source_metadata") if isinstance(package_item.get("source_metadata"), dict) else {}
        package_prefix = extract_package_prefix(package_file_name)
        temp_remote_path = client.resolve_remote_path(posixpath.join(PACKAGE_DEPLOY_DIR, package_file_name))
        remote_package_path = client.resolve_remote_path(posixpath.join(module_path, package_file_name))
        uploaded_file_paths.append(remote_package_path)
        if auto_deploy and client.path_exists(remote_package_path):
            package_summaries.append(
                {
                    "package_file_name": package_file_name,
                    "package_prefix": package_prefix,
                    "uploaded_file_path": remote_package_path,
                    "removed_files": [],
                    "source_kind": str(source_metadata.get("source_kind") or ""),
                    "source_path": str(source_metadata.get("source_path") or ""),
                    "download_path": str(source_metadata.get("download_path") or ""),
                    "skipped_existing": True,
                }
            )
            skipped_existing_files.append(remote_package_path)
            upload_progress_manager.update(
                upload_token,
                transferred_bytes=transferred_total,
                total_bytes=total_bytes,
                phase="preparing",
                message=f"[{package_index}/{len(package_files)}] 检测到同名文件，已跳过替换: {package_file_name}",
            )
            continue

        package_summary = {
            "package_file_name": package_file_name,
            "package_prefix": package_prefix,
            "uploaded_file_path": remote_package_path,
            "removed_files": [],
            "source_kind": str(source_metadata.get("source_kind") or ""),
            "source_path": str(source_metadata.get("source_path") or ""),
            "download_path": str(source_metadata.get("download_path") or ""),
            "skipped_existing": False,
        }
        package_summaries.append(package_summary)
        existing_entries = client.list_dir(module_path)
        for entry in existing_entries:
            if not entry.get("is_dir") and str(entry.get("name") or "").startswith(package_prefix):
                upload_progress_manager.update(
                    upload_token,
                    transferred_bytes=transferred_total,
                    total_bytes=total_bytes,
                    phase="preparing",
                    message=f"[{package_index}/{len(package_files)}] 正在清理旧包: {entry.get('name')}",
                )
        package_removed_files = client.remove_files_by_prefix(module_path, package_prefix, sudo_password=sudo_password)
        package_summary["removed_files"] = package_removed_files
        removed_files.extend(package_removed_files)
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=transferred_total,
            total_bytes=total_bytes,
            phase="uploading_to_robot",
            message=f"[{package_index}/{len(package_files)}] 正在上传到机器人: {temp_remote_path}",
        )

        def progress_callback(transferred_bytes: int, _: int) -> None:
            upload_progress_manager.update(
                upload_token,
                transferred_bytes=transferred_total + transferred_bytes,
                total_bytes=total_bytes,
                phase="uploading_to_robot",
                message=f"[{package_index}/{len(package_files)}] 正在上传到机器人: {temp_remote_path}",
            )

        client.upload_bytes(package_file_bytes, temp_remote_path, progress_callback=progress_callback)
        move_result = client.move_remote_path(temp_remote_path, remote_package_path, sudo_password=sudo_password)
        package_summary["move_result"] = move_result
        transferred_total += len(package_file_bytes)
    upload_progress_manager.update(
        upload_token,
        transferred_bytes=transferred_total,
        total_bytes=total_bytes,
        phase="completed",
        message=f"模块安装包已全部上传到机器人，共 {len(package_files)} 个",
        done=True,
    )
    return {
        "package_files": package_summaries,
        "removed_files": removed_files,
        "uploaded_file_paths": uploaded_file_paths,
        "uploaded_file_path": uploaded_file_paths[0] if uploaded_file_paths else "",
        "skipped_existing_files": skipped_existing_files,
        "total_bytes": total_bytes,
        "result": {"exit_code": 0, "stdout": "模块安装包上传完成", "stderr": ""},
    }


def module_install(
    client,
    *,
    module_name: str,
    module_path: str,
    install_template: str,
    uploaded_file_paths: list[str],
) -> dict[str, Any]:
    compose_profiles = client.get_interactive_env("COMPOSE_PROFILES")
    last_package_path = uploaded_file_paths[-1] if uploaded_file_paths else ""
    last_package_file_name = posixpath.basename(last_package_path) if last_package_path else ""
    last_package_prefix = extract_package_prefix(last_package_file_name) if last_package_file_name else ""
    install_command = render_remote_command(
        install_template,
        module_path,
        {
            "module_name": module_name,
            "module_path": module_path,
            "compose_profiles": compose_profiles,
            "package_file_name": last_package_file_name,
            "package_prefix": last_package_prefix,
            "package_path": last_package_path,
        },
        append_remote_path_if_missing=False,
    )
    result = client.exec_noninteractive_command(install_command)
    return {
        "module_name": module_name,
        "module_path": module_path,
        "compose_profiles": compose_profiles,
        "install_command": install_command,
        "package_file_name": last_package_file_name,
        "package_prefix": last_package_prefix,
        "package_path": last_package_path,
        "result": result,
    }


def module_start(
    client,
    *,
    module_name: str,
    module_path: str,
    start_command: str,
    up_wait_seconds: int,
) -> dict[str, Any]:
    wait_seconds = max(int(up_wait_seconds or 0), 0)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    if not str(start_command or "").strip():
        return {
            "module_name": module_name,
            "module_path": module_path,
            "wait_seconds": wait_seconds,
            "skipped": True,
            "result": {"exit_code": 0, "stdout": "", "stderr": ""},
        }
    result = client.exec_noninteractive_command(start_command)
    return {
        "module_name": module_name,
        "module_path": module_path,
        "wait_seconds": wait_seconds,
        "skipped": False,
        "command": start_command,
        "result": result,
    }


def module_health_check(
    client,
    *,
    module_name: str,
    module_path: str,
    health_command: str,
    rollback_template: str,
    auto_rollback: bool,
) -> dict[str, Any]:
    resolved_rollback_command = ""
    if str(rollback_template or "").strip():
        resolved_rollback_command = render_remote_command(
            rollback_template,
            module_path,
            {"module_name": module_name, "module_path": module_path},
            append_remote_path_if_missing=False,
        )
    if not str(health_command or "").strip():
        return {
            "module_name": module_name,
            "module_path": module_path,
            "skipped": True,
            "rollback_command": resolved_rollback_command,
            "result": {"exit_code": 0, "stdout": "", "stderr": ""},
        }
    health_result = client.exec_noninteractive_command(health_command)
    rollback_result = None
    if int(health_result.get("exit_code") or 0) != 0 and auto_rollback and resolved_rollback_command:
        rollback_result = client.exec_noninteractive_command(resolved_rollback_command)
    return {
        "module_name": module_name,
        "module_path": module_path,
        "skipped": False,
        "health_command": health_command,
        "rollback_command": resolved_rollback_command,
        "auto_rollback": bool(auto_rollback),
        "result": health_result,
        "rollback_result": rollback_result,
    }
