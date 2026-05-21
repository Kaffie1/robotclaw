from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable
from typing import Any

from ...common import extract_package_prefix, get_runtime_logger, render_remote_command
from ...core.config import PACKAGE_DEPLOY_DIR
from ...operations.workflow import probe_remote_package_supports_credentials
from ...shared.files import materialize_package_bytes_from_source
from ...shared.runtime import upload_progress_manager
from ..common import build_command_output_text

logger = get_runtime_logger()


def _normalize_source_items(source_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in source_items or []:
        if not isinstance(item, dict):
            continue
        source_metadata = item.get("source_metadata") if isinstance(item.get("source_metadata"), dict) else item
        if not isinstance(source_metadata, dict):
            continue
        normalized_items.append({"source_metadata": dict(source_metadata)})
    return normalized_items


def _artifact_item_local_path(item: dict[str, Any]) -> str:
    local_tmp_path = str(item.get("local_tmp_path") or "").strip()
    if local_tmp_path:
        return local_tmp_path
    source_metadata = item.get("source_metadata") if isinstance(item.get("source_metadata"), dict) else {}
    return str(source_metadata.get("local_tmp_path") or "").strip()


def _artifact_item_size(item: dict[str, Any]) -> int:
    explicit_size = item.get("file_size")
    if explicit_size is None:
        explicit_size = item.get("package_file_size")
    try:
        normalized_size = int(explicit_size or 0)
    except (TypeError, ValueError):
        normalized_size = 0
    return max(normalized_size, 0)


def _artifact_item_name(item: dict[str, Any]) -> str:
    return str(item.get("file_name") or item.get("package_file_name") or "").strip()


def prepare_artifact_sources(
    source_items: list[dict[str, Any]],
    *,
    upload_token: str,
) -> dict[str, Any]:
    """准备部署安装包来源信息列表，支持文件服务器路径和本地上传两种来源，
        每个来源项会解析出文件名、字节内容等元信息，必要时从文件服务器下载到本地临时目录。"""
    normalized_items = _normalize_source_items(source_items)
    if not normalized_items:
        raise ValueError("缺少可用的安装包来源")
    prepared_items: list[dict[str, Any]] = []
    total_bytes = 0
    total_count = len(normalized_items)
    for index, source_item in enumerate(normalized_items, start=1):
        source_metadata = dict(source_item.get("source_metadata") or {})
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
                message=f"[{index}/{total_count}] 正在准备安装包来源",
            )
        file_name, file_bytes, resolved_source_metadata = materialize_package_bytes_from_source(
            source_metadata,
            local_error_message="请选择要部署的安装包文件或填写文件服务器包路径",
        )
        file_size = max(int(resolved_source_metadata.get("file_size") or len(file_bytes) or 0), 0)
        total_bytes += file_size
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=total_bytes if source_kind == "file_server" else 0,
            total_bytes=total_bytes,
            phase="queued",
            message=f"[{index}/{total_count}] 安装包已准备完成: {file_name}",
        )
        prepared_items.append(
            {
                "file_name": file_name,
                "source_metadata": resolved_source_metadata,
                "file_size": file_size,
                "source_kind": str(resolved_source_metadata.get("source_kind") or "").strip(),
                "download_path": str(resolved_source_metadata.get("download_path") or "").strip(),
                "local_tmp_path": str(resolved_source_metadata.get("local_tmp_path") or "").strip(),
                "package_file_name": file_name,
                "package_file_size": file_size,
            }
        )
    first_item = prepared_items[0]
    return {
        "artifact_items": prepared_items,
        "artifact_count": len(prepared_items),
        "total_bytes": total_bytes,
        "file_names": [str(item.get("file_name") or "") for item in prepared_items],
        "file_name": str(first_item.get("file_name") or ""),
        "file_size": int(first_item.get("file_size") or 0),
        "source_metadata": first_item.get("source_metadata") or {},
        "source_kind": str(first_item.get("source_kind") or "").strip(),
        "download_path": str(first_item.get("download_path") or "").strip(),
        "local_tmp_path": str(first_item.get("local_tmp_path") or "").strip(),
        "package_files": [
            {
                "package_file_name": str(item.get("package_file_name") or ""),
                "package_file_size": int(item.get("package_file_size") or item.get("file_size") or 0),
                "local_tmp_path": str(item.get("local_tmp_path") or ""),
                "source_metadata": item.get("source_metadata") or {},
            }
            for item in prepared_items
        ],
    }

def remote_stage_artifacts(
    client,
    *,
    target_root: str,
    target_mode: str,
    artifact_items: list[dict[str, Any]],
    cleanup_existing_remote_files: bool,
    auto_deploy: bool,
    upload_token: str,
    sudo_password: str,
) -> dict[str, Any]:
    normalized_target_mode = str(target_mode or "directory").strip().lower() or "directory"
    if normalized_target_mode == "exact_path":
        if len(artifact_items) != 1:
            raise ValueError("精确路径上传模式要求且仅允许一个安装包")
        artifact = artifact_items[0]
        file_name = _artifact_item_name(artifact)
        local_tmp_path = _artifact_item_local_path(artifact)
        file_size = _artifact_item_size(artifact)
        if not file_name or not local_tmp_path or file_size <= 0:
            raise ValueError("精确路径上传缺少 file_name、local_tmp_path 或 file_size")
        resolved_remote_path = client.resolve_remote_path(target_root)
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
            total_bytes=file_size,
            phase="uploading_to_robot",
            message=f"正在上传到目标处理器: {resolved_remote_path}",
        )
        client.upload_local_file(local_tmp_path, resolved_remote_path, progress_callback=progress_callback)
        output = f"安装包已上传到机器人: {resolved_remote_path}"
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=file_size,
            total_bytes=file_size,
            phase="completed",
            message=output,
            done=True,
        )
        return {
            "remote_deb_path": target_root,
            "resolved_remote_path": resolved_remote_path,
            "remote_dir": remote_dir,
            "removed_files": removed_files,
            "upload_skipped": False,
            "cleanup_existing_remote_files": cleanup_existing_remote_files,
            "uploaded_bytes": file_size,
            "result": {"exit_code": 0, "stdout": output, "stderr": ""},
            "output": output,
        }

    if normalized_target_mode != "directory":
        raise ValueError(f"不支持的目标模式: {target_mode}")
    if not artifact_items:
        raise ValueError("目录上传模式缺少安装包列表")

    total_bytes = sum(_artifact_item_size(item) for item in artifact_items)
    transferred_total = 0
    package_summaries: list[dict[str, Any]] = []
    removed_files: list[str] = []
    uploaded_file_paths: list[str] = []
    skipped_existing_files: list[str] = []
    upload_progress_manager.update(
        upload_token,
        total_bytes=total_bytes,
        phase="preparing",
        message="部署任务已创建，准备清理旧包",
    )
    total_count = len(artifact_items)
    for package_index, artifact in enumerate(artifact_items, start=1):
        package_file_name = _artifact_item_name(artifact)
        local_tmp_path = _artifact_item_local_path(artifact)
        package_file_size = _artifact_item_size(artifact)
        source_metadata = artifact.get("source_metadata") if isinstance(artifact.get("source_metadata"), dict) else {}
        if not package_file_name or not local_tmp_path or package_file_size <= 0:
            raise ValueError("目录上传模式缺少 package_file_name/file_name、local_tmp_path 或 file_size")
        package_prefix = extract_package_prefix(package_file_name)
        temp_remote_path = client.resolve_remote_path(posixpath.join(PACKAGE_DEPLOY_DIR, package_file_name))
        remote_package_path = client.resolve_remote_path(posixpath.join(target_root, package_file_name))
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
                message=f"[{package_index}/{total_count}] 检测到同名文件，已跳过替换: {package_file_name}",
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
        existing_entries = client.list_dir(target_root)
        for entry in existing_entries:
            if not entry.get("is_dir") and str(entry.get("name") or "").startswith(package_prefix):
                upload_progress_manager.update(
                    upload_token,
                    transferred_bytes=transferred_total,
                    total_bytes=total_bytes,
                    phase="preparing",
                    message=f"[{package_index}/{total_count}] 正在清理旧包: {entry.get('name')}",
                )
        package_removed_files = client.remove_files_by_prefix(target_root, package_prefix, sudo_password=sudo_password)
        package_summary["removed_files"] = package_removed_files
        removed_files.extend(package_removed_files)
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=transferred_total,
            total_bytes=total_bytes,
            phase="uploading_to_robot",
            message=f"[{package_index}/{total_count}] 正在上传到机器人: {temp_remote_path}",
        )

        def progress_callback(transferred_bytes: int, _: int) -> None:
            upload_progress_manager.update(
                upload_token,
                transferred_bytes=transferred_total + transferred_bytes,
                total_bytes=total_bytes,
                phase="uploading_to_robot",
                message=f"[{package_index}/{total_count}] 正在上传到机器人: {temp_remote_path}",
            )

        client.upload_local_file(local_tmp_path, temp_remote_path, progress_callback=progress_callback)
        move_result = client.move_remote_path(temp_remote_path, remote_package_path, sudo_password=sudo_password)
        package_summary["move_result"] = move_result
        transferred_total += package_file_size

    upload_progress_manager.update(
        upload_token,
        transferred_bytes=transferred_total,
        total_bytes=total_bytes,
        phase="completed",
        message=f"安装包已全部上传到机器人，共 {len(artifact_items)} 个",
        done=True,
    )
    return {
        "package_files": package_summaries,
        "removed_files": removed_files,
        "uploaded_file_paths": uploaded_file_paths,
        "uploaded_file_path": uploaded_file_paths[0] if uploaded_file_paths else "",
        "skipped_existing_files": skipped_existing_files,
        "total_bytes": total_bytes,
        "target_root": client.resolve_remote_path(target_root),
        "target_mode": normalized_target_mode,
        "result": {"exit_code": 0, "stdout": "安装包上传完成", "stderr": ""},
    }


def _parse_options_from_output(output: str) -> list[dict[str, str]]:
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


def _extract_inferred_option_from_probe_logs(output: str) -> str:
    match = re.search(r"global=([A-Za-z0-9_]+)", str(output or ""))
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _filter_options_by_fallback(
    parsed_options: list[dict[str, str]],
    fallback_options: list[dict[str, str]],
) -> list[dict[str, str]]:
    allowed_values = {
        str(option.get("value") or "").strip()
        for option in fallback_options
        if isinstance(option, dict) and str(option.get("value") or "").strip()
    }
    if not allowed_values:
        return parsed_options
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for option in parsed_options:
        if not isinstance(option, dict):
            continue
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or value).strip()
        if not value or value not in allowed_values or value in seen:
            continue
        seen.add(value)
        normalized.append({"value": value, "label": label or value})
    return normalized


def _normalize_fallback_options(fallback_value: Any) -> list[dict[str, str]]:
    return [
        {
            "value": str(option.get("value") or "").strip(),
            "label": str(option.get("label") or option.get("value") or "").strip(),
        }
        for option in (fallback_value or [])
        if isinstance(option, dict) and str(option.get("value") or "").strip()
    ]

def _resolve_primary_remote_path(client, command_args: dict[str, Any]) -> str:
    for key in ("deb_path", "remote_path", "path", "package_path"):
        value = str(command_args.get(key) or "").strip()
        if value:
            return client.resolve_remote_path(value)
    for key, value in command_args.items():
        if not str(key or "").endswith("_path"):
            continue
        normalized_value = str(value or "").strip()
        if normalized_value:
            return client.resolve_remote_path(normalized_value)
    raise ValueError("命令参数中缺少可用于渲染的远端路径")


def _normalize_target_credentials_probe(probe_config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(probe_config, dict):
        return None
    removable_args = [
        str(item or "").strip()
        for item in (probe_config.get("removable_args") or [])
        if str(item or "").strip()
    ]
    if not removable_args:
        return None
    return {"removable_args": removable_args}


def _strip_command_args(command_template: str, removable_args: list[str]) -> str:
    normalized_template = str(command_template or "")
    for arg in removable_args:
        normalized_template = normalized_template.replace(f" {arg}", " ")
        normalized_template = normalized_template.replace(arg, "")
    return re.sub(r"\s{2,}", " ", normalized_template).strip()


def _render_execution_command(
    client,
    *,
    command_template: str,
    command_args: dict[str, Any],
    resolved_path: str,
    device_type: str,
    target_username: str,
    target_password: str,
    target_credentials_probe: dict[str, Any] | None,
) -> tuple[str, bool | None]:
    normalized_probe = _normalize_target_credentials_probe(target_credentials_probe)
    if not normalized_probe:
        return (
            render_remote_command(
                str(command_template or ""),
                resolved_path,
                command_args,
                append_remote_path_if_missing=False,
            ),
            None,
        )

    supports_target_credentials = probe_remote_package_supports_credentials(client, resolved_path)
    effective_command_template = str(command_template or "")
    if not supports_target_credentials:
        effective_command_template = _strip_command_args(
            effective_command_template,
            list(normalized_probe.get("removable_args") or []),
        )
    rendered_command = render_remote_command(
        effective_command_template,
        resolved_path,
        {
            **dict(command_args or {}),
            "device_type": str(device_type or "").upper(),
            "target_username": str(target_username or ""),
            "target_password": str(target_password or ""),
        },
        append_remote_path_if_missing=False,
    )
    return rendered_command, supports_target_credentials


def _execute_command_with_failure_policy(
    client,
    *,
    rendered_command: str,
    timeout_seconds: int,
    on_failure: str,
    output_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    try:
        return client.exec_noninteractive_command(
            rendered_command,
            timeout=float(max(int(timeout_seconds or 0), 1)),
            output_callback=output_callback,
        )
    except Exception as exc:  # noqa: BLE001
        if on_failure == "raise":
            raise
        return {"exit_code": 1, "stdout": "", "stderr": str(exc)}


def _build_options_payload(
    result: dict[str, Any],
    output: str,
    *,
    on_failure: str,
    fallback_value: Any,
) -> dict[str, Any]:
    fallback_options = _normalize_fallback_options(fallback_value)
    parsed_options = _filter_options_by_fallback(_parse_options_from_output(output), fallback_options)
    inferred_value = _extract_inferred_option_from_probe_logs(output)
    warning = ""
    options = parsed_options

    if int(result.get("exit_code") or 0) != 0:
        if on_failure == "use_fallback":
            options = fallback_options
            warning = "选项探测命令执行失败，已回退到默认选项列表，请确认后继续部署"
    elif not options and inferred_value:
        options = fallback_options or [{"value": inferred_value, "label": inferred_value}]
        warning = f"探测命令未返回标准选项列表，已根据日志识别为 {inferred_value}"
    elif not options and on_failure == "use_fallback":
        options = fallback_options
        warning = "命令未返回可选项，已回退到默认选项列表，请确认后继续部署"

    return {
        "options": options,
        "inferred_value": inferred_value,
        "warning": warning,
    }


def _build_execute_payload(
    *,
    rendered_command: str,
    resolved_path: str,
    result: dict[str, Any],
    parse_mode: str,
    on_failure: str,
    fallback_value: Any,
    supports_target_credentials: bool | None,
) -> dict[str, Any]:
    output = build_command_output_text(result)
    payload: dict[str, Any] = {
        "command": rendered_command,
        "resolved_path": resolved_path,
        "result": result,
        "output": output,
        "parse_mode": parse_mode,
        "on_failure": on_failure,
    }
    if supports_target_credentials is not None:
        payload["supports_target_credentials"] = supports_target_credentials
    if parse_mode in {"options", "machine_options"}:
        payload.update(
            _build_options_payload(
                result,
                output,
                on_failure=on_failure,
                fallback_value=fallback_value,
            )
        )
    elif parse_mode == "command_result" and int(result.get("exit_code") or 0) != 0 and on_failure == "use_fallback":
        payload["fallback_value"] = fallback_value
    return payload


def remote_execute_with_fallback(
    client,
    *,
    command_template: str,
    command_args: dict[str, Any],
    parse_mode: str,
    on_failure: str,
    fallback_value: Any,
    timeout_seconds: int,
    device_type: str,
    target_username: str,
    target_password: str,
    target_credentials_probe: dict[str, Any] | None = None,
    output_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    normalized_command_args = dict(command_args or {})
    normalized_parse_mode = str(parse_mode or "command_result").strip().lower() or "command_result"
    normalized_on_failure = str(on_failure or "raise").strip().lower() or "raise"
    resolved_path = _resolve_primary_remote_path(client, normalized_command_args)
    rendered_command, supports_target_credentials = _render_execution_command(
        client,
        command_template=str(command_template or ""),
        command_args=normalized_command_args,
        resolved_path=resolved_path,
        device_type=str(device_type or "").upper(),
        target_username=str(target_username or ""),
        target_password=str(target_password or ""),
        target_credentials_probe=target_credentials_probe,
    )
    result = _execute_command_with_failure_policy(
        client,
        rendered_command=rendered_command,
        timeout_seconds=timeout_seconds,
        on_failure=normalized_on_failure,
        output_callback=output_callback,
    )
    return _build_execute_payload(
        rendered_command=rendered_command,
        resolved_path=resolved_path,
        result=result,
        parse_mode=normalized_parse_mode,
        on_failure=normalized_on_failure,
        fallback_value=fallback_value,
        supports_target_credentials=supports_target_credentials,
    )
