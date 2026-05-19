from __future__ import annotations

import shlex
import time
from typing import Any

from ...core.config import MODULE_DEPLOY_NAMES, MODULE_DEPLOY_PROJECT_ROOT
from ...core.models import ApiError
from ...common import get_fault_logger, short_error
from ..common import build_command_output_text

logger = get_fault_logger()


def resolve_module_project_root(client, module_name: str) -> tuple[Any, str, str]:
    normalized_module_name = str(module_name or "").strip()
    if normalized_module_name not in MODULE_DEPLOY_NAMES:
        raise ApiError(f"不支持的模块: {normalized_module_name}")
    project_root = client.resolve_remote_path(MODULE_DEPLOY_PROJECT_ROOT)
    if not client.path_exists(project_root) or not client.is_dir_path(project_root):
        raise ApiError(f"机器人项目目录不存在: {project_root}")
    return client, normalized_module_name, project_root


def execute_compose_service_command(
    client,
    project_root: str,
    service_name: str,
    command: str,
    *,
    timeout_seconds: int = 30,
    setup_script: str = "",
) -> dict[str, Any]:
    normalized_project_root = client.resolve_remote_path(project_root)
    normalized_service_name = str(service_name or "").strip()
    normalized_command = str(command or "").strip()
    if not normalized_project_root:
        raise ApiError("docker compose 项目目录不能为空")
    if not normalized_service_name:
        raise ApiError("docker compose 服务名不能为空")
    if not normalized_command:
        raise ApiError("容器内命令不能为空")
    timeout_seconds = max(int(timeout_seconds or 0), 1)
    shell_command = normalized_command if not setup_script else f"{setup_script}; {normalized_command}"
    wrapped_command = (
        f"cd {shlex.quote(normalized_project_root)} && "
        f"docker compose exec -T {shlex.quote(normalized_service_name)} "
        f"bash -lc {shlex.quote(shell_command)} "
        "</dev/null"
    )
    return client.exec_interactive_command(wrapped_command, timeout=float(timeout_seconds) + 5.0)


def docker_compose_down_module(client, module_name: str) -> dict[str, Any]:
    client, normalized_module_name, project_root = resolve_module_project_root(client, module_name)
    command = f"cd {shlex.quote(project_root)} && docker compose down {shlex.quote(normalized_module_name)}"
    result = client.exec_interactive_command(command, timeout=20.0)
    if int(result.get("exit_code") or 0) != 0:
        raise ApiError(f"停止模块服务失败: {short_error(result)}")
    return {
        "module_name": normalized_module_name,
        "project_root": project_root,
        "command": command,
        "result": result,
        "output": build_command_output_text(result),
    }


def docker_compose_up_module(client, module_name: str, *, wait_seconds: int = 0) -> dict[str, Any]:
    client, normalized_module_name, project_root = resolve_module_project_root(client, module_name)
    wait_seconds = max(int(wait_seconds or 0), 0)
    command = f"cd {shlex.quote(project_root)} && docker compose up -d {shlex.quote(normalized_module_name)}"
    result = client.exec_interactive_command(command, timeout=20.0)
    if int(result.get("exit_code") or 0) != 0:
        raise ApiError(f"启动模块服务失败: {short_error(result)}")
    if wait_seconds:
        logger.info("docker_compose_up_module 等待容器稳定 | module=%s | seconds=%d", normalized_module_name, wait_seconds)
        time.sleep(wait_seconds)
    return {
        "module_name": normalized_module_name,
        "project_root": project_root,
        "command": command,
        "result": result,
        "output": build_command_output_text(result),
        "wait_seconds": wait_seconds,
    }


def docker_compose_exec_command(
    client,
    project_root: str,
    service_name: str,
    command: str,
    *,
    timeout_seconds: int = 30,
    device_type: str = "",
) -> dict[str, Any]:
    result = execute_compose_service_command(
        project_root,
        service_name,
        command,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    return {
        "service_name": str(service_name or "").strip(),
        "project_root": client.resolve_remote_path(project_root),
        "command": str(command or "").strip(),
        "timeout_seconds": max(int(timeout_seconds or 0), 1),
        "result": result,
        "output": build_command_output_text(result),
        "device_type": str(device_type or "").upper(),
    }
