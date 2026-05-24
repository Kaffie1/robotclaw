from __future__ import annotations

import shlex
from typing import Any

from ...core.config import MODULE_DEPLOY_NAMES, MODULE_DEPLOY_PROJECT_ROOT
from ...core.models import ApiError
from ...shared import get_runtime_logger, short_error
from ..common import build_command_output_text

logger = get_runtime_logger()


def _build_module_compose_env_prefix(compose_profiles: str) -> str:
    normalized_profiles = str(compose_profiles or "").strip()
    if not normalized_profiles:
        return ""
    ros_master_uri = "http://192.168.217.100:11311" if normalized_profiles == "rx" else "http://192.168.217.1:11311"
    return (
        f"export COMPOSE_PROFILES={shlex.quote(normalized_profiles)}; "
        "export DISPLAY=${DISPLAY:-127.0.0.1:99.0}; "
        "export ROBOT_MODEL=$COMPOSE_PROFILES; "
        f"export ROS_MASTER_URI={shlex.quote(ros_master_uri)}; "
        "export ROS_IP=192.168.217.100; "
        "echo ROS_MASTER_URI=$ROS_MASTER_URI; "
        "echo ROS_IP=$ROS_IP; "
        "echo COMPOSE_PROFILES=$COMPOSE_PROFILES; "
    )


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
    compose_profiles = client.get_interactive_env("COMPOSE_PROFILES")
    env_prefix = _build_module_compose_env_prefix(compose_profiles)
    command = f"bash -lc {shlex.quote(env_prefix + f'cd {project_root} && docker compose down {normalized_module_name}')}"
    result = client.exec_noninteractive_command(command, timeout=20.0)
    if int(result.get("exit_code") or 0) != 0:
        raise ApiError(f"停止模块服务失败: {short_error(result)}")
    return {
        "module_name": normalized_module_name,
        "project_root": project_root,
        "compose_profiles": compose_profiles,
        "command": command,
        "result": result,
        "output": build_command_output_text(result),
    }


def docker_compose_up_module(client, module_name: str, *, wait_seconds: int = 0) -> dict[str, Any]:
    client, normalized_module_name, project_root = resolve_module_project_root(client, module_name)
    compose_profiles = client.get_interactive_env("COMPOSE_PROFILES")
    env_prefix = _build_module_compose_env_prefix(compose_profiles)
    command = f"bash -lc {shlex.quote(env_prefix + f'cd {project_root} && docker compose up -d {normalized_module_name}')}"
    result = client.exec_noninteractive_command(command, timeout=20.0)
    if int(result.get("exit_code") or 0) != 0:
        raise ApiError(f"启动模块服务失败: {short_error(result)}")
    return {
        "module_name": normalized_module_name,
        "project_root": project_root,
        "compose_profiles": compose_profiles,
        "command": command,
        "result": result,
        "output": build_command_output_text(result),
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
