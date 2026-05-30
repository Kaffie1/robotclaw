from __future__ import annotations

import shlex
from typing import Any

from backend.core.models import ApiError
from ..common import build_command_output_text


def ensure_readonly_remote_command(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        raise ApiError("命令不能为空")
    blocked_tokens = [
        " rm ",
        " mv ",
        " cp ",
        " chmod ",
        " chown ",
        " mkdir ",
        " rmdir ",
        " touch ",
        " sed -i",
        " docker compose up",
        " docker compose down",
        " docker restart",
        " systemctl ",
        " reboot",
        " shutdown",
        " kill ",
        " pkill ",
        " tee ",
        " dd ",
    ]
    padded_command = f" {normalized_command.lower()} "
    if any(token in padded_command for token in blocked_tokens):
        raise ApiError("只读执行工具不允许修改远端环境，请改用专用工具")
    if ">" in normalized_command or ">>" in normalized_command:
        raise ApiError("只读执行工具不支持重定向写入")
    return normalized_command


def ping_host(client, host: str, *, count: int = 1, timeout_seconds: int = 2) -> dict[str, Any]:
    normalized_host = str(host or "").strip()
    if not normalized_host:
        raise ApiError("ping 主机不能为空")
    count = max(int(count or 1), 1)
    timeout_seconds = max(int(timeout_seconds or 2), 1)
    command = f"ping -c {count} -W {timeout_seconds} {shlex.quote(normalized_host)}"
    result = client.exec_interactive_command(command, timeout=float(timeout_seconds) + 5.0)
    return {
        "host": normalized_host,
        "command": command,
        "result": result,
        "output": build_command_output_text(result),
    }


def remote_resolve_path(client, path: str) -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "exists": client.path_exists(resolved_path) if resolved_path else False,
    }


def remote_path_exists(client, path: str) -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "exists": client.path_exists(resolved_path),
        "is_dir": client.is_dir_path(resolved_path),
    }


def remote_list_dir(client, path: str) -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    return {
        "entries": client.list_dir(resolved_path),
        "resolved_path": resolved_path,
    }


def remote_scan_paths(client, root: str, keyword: str, session: dict[str, Any]) -> dict[str, Any]:
    resolved_root = client.resolve_remote_path(root)
    entries = client.walk_entries(resolved_root)
    all_paths = [resolved_root, *[entry["path"] for entry in entries]]
    all_directories = [resolved_root, *[entry["path"] for entry in entries if entry["is_dir"]]]
    session["path_cache"] = all_paths
    normalized_keyword = str(keyword or "").strip().lower()
    if normalized_keyword:
        paths = [item for item in all_paths if normalized_keyword in item.lower()]
        directories = [item for item in all_directories if normalized_keyword in item.lower()]
    else:
        paths = all_paths
        directories = all_directories
    return {
        "count": len(paths),
        "paths": paths,
        "directories": directories,
        "resolved_root": resolved_root,
    }


def remote_shortcuts(client, *, should_cache: bool, session: dict[str, Any]) -> dict[str, Any]:
    shortcut_payload = client.directory_shortcuts()
    if should_cache:
        session["remote_shortcuts"] = shortcut_payload["shortcuts"]
        session["preferred_root"] = shortcut_payload["preferred_root"]
    return shortcut_payload


def remote_execute_readonly(client, command: str, *, interactive: bool = False, timeout_seconds: int = 30) -> dict[str, Any]:
    readonly_command = ensure_readonly_remote_command(command)
    timeout_seconds = max(int(timeout_seconds or 0), 1)
    result = (
        client.exec_interactive_command(readonly_command, timeout=float(timeout_seconds))
        if interactive
        else client.exec_command(readonly_command, timeout=float(timeout_seconds))
    )
    return {
        "command": readonly_command,
        "interactive": bool(interactive),
        "timeout_seconds": timeout_seconds,
        "result": result,
        "output": build_command_output_text(result),
    }


def remote_execute_command(client, command: str, *, interactive: bool = False, timeout_seconds: int = 30) -> dict[str, Any]:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        raise ApiError("命令不能为空")
    timeout_seconds = max(int(timeout_seconds or 0), 1)
    result = client.exec_interactive_command(normalized_command, timeout=float(timeout_seconds)) if interactive else client.exec_command(normalized_command, timeout=float(timeout_seconds))
    return {
        "command": normalized_command,
        "interactive": bool(interactive),
        "timeout_seconds": timeout_seconds,
        "result": result,
        "output": build_command_output_text(result),
    }


def remote_get_interactive_env(client, name: str, *, timeout_seconds: int = 10) -> dict[str, Any]:
    variable_name = str(name or "").strip()
    if not variable_name:
        raise ApiError("环境变量名不能为空")
    timeout_seconds = max(int(timeout_seconds or 0), 1)
    value = client.get_interactive_env(variable_name, timeout=float(timeout_seconds))
    return {
        "name": variable_name,
        "value": value,
        "timeout_seconds": timeout_seconds,
    }


def remote_ensure_executable(client, path: str, *, sudo_password: str = "") -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    result = client.ensure_remote_executable(resolved_path, sudo_password=sudo_password)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "result": result,
        "output": build_command_output_text(result),
    }


def remote_read_file(client, path: str) -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    raw_bytes = client.read_file_bytes(resolved_path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "size": len(raw_bytes),
        "content": raw_bytes.decode("utf-8", errors="replace"),
    }


def remote_get_file_owner(client, path: str) -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "owner": client.get_remote_file_owner(resolved_path),
    }


def remote_backup_path(client, path: str, *, sudo_password: str = "") -> dict[str, Any]:
    resolved_path = client.resolve_remote_path(path)
    backup_path = client.backup_remote_path(resolved_path, sudo_password=sudo_password)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "backup_path": backup_path or "",
        "backed_up": bool(backup_path),
    }


def remote_restore_backup(client, path: str, backup_path: str) -> dict[str, Any]:
    normalized_backup_path = client.resolve_remote_path(backup_path)
    resolved_path = client.resolve_remote_path(path)
    result = client.restore_backup(normalized_backup_path, resolved_path)
    return {
        "path": path,
        "resolved_path": resolved_path,
        "backup_path": normalized_backup_path,
        "result": result,
        "output": build_command_output_text(result),
    }


def remote_remove_files_by_prefix(client, remote_dir: str, prefix: str, *, sudo_password: str = "") -> dict[str, Any]:
    normalized_remote_dir = client.resolve_remote_path(remote_dir)
    normalized_prefix = str(prefix or "").strip()
    if not normalized_prefix:
        raise ApiError("prefix 不能为空")
    removed_files = client.remove_files_by_prefix(normalized_remote_dir, normalized_prefix, sudo_password=sudo_password)
    return {
        "remote_dir": normalized_remote_dir,
        "prefix": normalized_prefix,
        "removed_files": removed_files,
        "removed_count": len(removed_files),
    }
