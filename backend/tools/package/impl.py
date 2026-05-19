from __future__ import annotations

import json
import posixpath
from collections.abc import Callable
from typing import Any

from ...common import get_fault_logger
from ...operations.deploy import probe_remote_package_supports_credentials, render_package_install_command
from ...shared.files import materialize_package_bytes_from_source
from ...shared.runtime import upload_progress_manager
from ..common import build_command_output_text

logger = get_fault_logger()


def package_prepare_source(
    source_metadata: dict[str, Any],
    *,
    upload_token: str,
) -> dict[str, object]:
    normalized_source_metadata = dict(source_metadata or {})
    if str(normalized_source_metadata.get("source_kind") or "").strip() == "file_server":
        upload_progress_manager.update(
            upload_token,
            phase="downloading_from_server",
            message=f"正在从文件服务器下载: {normalized_source_metadata.get('download_path') or normalized_source_metadata.get('source_path')}",
        )
    else:
        upload_progress_manager.update(
            upload_token,
            phase="preparing",
            message="正在准备本地上传的安装包",
        )

    file_name, file_bytes, resolved_source_metadata = materialize_package_bytes_from_source(
        normalized_source_metadata,
        local_error_message="请选择要部署的安装包文件或填写文件服务器包路径",
    )
    if str(resolved_source_metadata.get("source_kind") or "").strip() == "file_server":
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=len(file_bytes),
            total_bytes=len(file_bytes),
            phase="queued",
            message="文件已从服务器下载，准备上传到目标处理器",
        )
    else:
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=0,
            total_bytes=len(file_bytes),
            phase="queued",
            message="部署任务已创建，准备上传到目标处理器",
        )
    return {
        "file_name": file_name,
        "source_metadata": resolved_source_metadata,
        "file_size": len(file_bytes),
        "source_kind": str(resolved_source_metadata.get("source_kind") or "").strip(),
        "download_path": str(resolved_source_metadata.get("download_path") or "").strip(),
        "local_tmp_path": str(resolved_source_metadata.get("local_tmp_path") or "").strip(),
        "_file_bytes": file_bytes,
    }


def package_probe_credentials(client, path: str) -> dict[str, str | bool]:
    resolved_path = client.resolve_remote_path(path)
    supported = probe_remote_package_supports_credentials(client, resolved_path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "supports_target_credentials": supported,
    }


def _parse_machine_options_from_output(output: str) -> list[dict[str, str]]:
    normalized = str(output or "").replace("\r", "\n")
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        candidates = [str(item or "").strip() for item in parsed if str(item or "").strip()]
    else:
        candidates = [
            item.strip().strip("[]\"'")
            for chunk in normalized.splitlines()
            for item in chunk.split(",")
            if item.strip().strip("[]\"'")
        ]
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        options.append({"value": item, "label": item})
    return options


def package_probe_machine_types(
    client,
    deb_path: str,
    *,
    probe_command_template: str,
    fallback_machine_options: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """探测安装包支持的机型，优先使用安装包内置的探测命令，失败时回退到默认机型列表"""
    resolved_path = client.resolve_remote_path(deb_path)
    command = str(probe_command_template or "").strip() or "chmod +x {deb_path} && {deb_path} --quiet -- support_robot_types"
    rendered_command = command.replace("{deb_path}", resolved_path)
    probe_result = client.exec_noninteractive_command(rendered_command, timeout=20.0)
    probe_output = "\n".join(
        part
        for part in [str(probe_result.get("stdout") or "").strip(), str(probe_result.get("stderr") or "").strip()]
        if part
    )
    logger.debug(f"Probe command executed: {probe_output}")
    parsed_options = _parse_machine_options_from_output(probe_output)
    normalized_fallback = [
        {"value": str(option.get("value") or "").strip(), "label": str(option.get("label") or option.get("value") or "").strip()}
        for option in (fallback_machine_options or [])
        if isinstance(option, dict) and str(option.get("value") or "").strip()
    ]
    warning = ""
    machine_options = parsed_options
    if int(probe_result.get("exit_code") or 0) != 0:
        machine_options = normalized_fallback
        warning = "机型探测命令执行失败，已回退到默认机型列表，请确认后继续部署"
    elif not machine_options:
        machine_options = normalized_fallback
        warning = "安装包未返回可选机型，已回退到默认机型列表，请确认后继续部署"
    return {
        "deb_path": deb_path,
        "resolved_path": resolved_path,
        "command": rendered_command,
        "result": probe_result,
        "output": probe_output,
        "machine_options": machine_options,
        "warning": warning,
    }


def package_stage_remote(
    client,
    remote_deb_path: str,
    *,
    file_name: str,
    file_bytes: bytes,
    cleanup_existing_remote_files: bool,
    upload_token: str,
) -> dict[str, object]:
    resolved_remote_path = client.resolve_remote_path(remote_deb_path)
    remote_dir = posixpath.dirname(resolved_remote_path)
    removed_files: list[str] = []

    def progress_callback(transferred_bytes: int, total_bytes: int) -> None:
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=transferred_bytes,
            total_bytes=total_bytes,
            phase="uploading_to_robot",
            message=f"正在上传到目标处理器: {resolved_remote_path}",
        )

    if cleanup_existing_remote_files and client.path_exists(resolved_remote_path):
        client.remove_remote_path(resolved_remote_path)
        removed_files = [resolved_remote_path]
    upload_progress_manager.update(
        upload_token,
        transferred_bytes=0,
        total_bytes=len(file_bytes),
        phase="uploading_to_robot",
        message=f"正在上传到目标处理器: {resolved_remote_path}",
    )
    client.upload_bytes(file_bytes, resolved_remote_path, progress_callback=progress_callback)
    output = f"安装包已上传到机器人: {resolved_remote_path}"
    upload_progress_manager.update(
        upload_token,
        transferred_bytes=len(file_bytes),
        total_bytes=len(file_bytes),
        phase="completed",
        message=output,
        done=True,
    )
    return {
        "remote_deb_path": remote_deb_path,
        "resolved_remote_path": resolved_remote_path,
        "remote_dir": remote_dir,
        "removed_files": removed_files,
        "upload_skipped": False,
        "cleanup_existing_remote_files": cleanup_existing_remote_files,
        "uploaded_bytes": len(file_bytes),
        "result": {"exit_code": 0, "stdout": output, "stderr": ""},
        "output": output,
    }


def package_install(
    client,
    deb_path: str,
    *,
    machine_type: str = "",
    install_template: str,
    timeout_seconds: int,
    device_type: str,
    target_username: str,
    target_password: str,
    output_callback: Callable[[str], None] | None = None,
) -> dict[str, object]:
    resolved_path = client.resolve_remote_path(deb_path)
    supports_target_credentials = probe_remote_package_supports_credentials(client, resolved_path)
    command = render_package_install_command(
        str(install_template or ""),
        resolved_path,
        machine_type=str(machine_type or "").strip(),
        device_type=str(device_type or "").upper(),
        target_username=str(target_username or ""),
        target_password=str(target_password or ""),
        include_target_credentials=supports_target_credentials,
    )
    timeout_seconds = max(int(timeout_seconds or 0), 1)
    result = client.exec_noninteractive_command(command, timeout=float(timeout_seconds), output_callback=output_callback)
    return {
        "deb_path": deb_path,
        "resolved_path": resolved_path,
        "machine_type": str(machine_type or "").strip(),
        "supports_target_credentials": supports_target_credentials,
        "command": command,
        "timeout_seconds": timeout_seconds,
        "result": result,
        "output": build_command_output_text(result),
    }
