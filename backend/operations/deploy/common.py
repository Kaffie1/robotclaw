import os
import posixpath
import re
import shlex
from typing import Any

from ...core.config import PACKAGE_DEPLOY_DIR
from ...core.models import ApiError, ConnectionConfig
from ...common import render_remote_command, require_text
from ...infra import RobotClient
from ..services import ensure_client_connected, robot_identity


def render_package_install_command(
    template: str,
    remote_path: str,
    *,
    machine_type: str,
    device_type: str,
    target_username: str,
    target_password: str,
    include_target_credentials: bool,
) -> str:
    normalized_template = str(template or "")
    if not include_target_credentials:
        normalized_template = re.sub(r"\s+--user=\{target_username\}", "", normalized_template)
        normalized_template = re.sub(r"\s+--password=\{target_password\}", "", normalized_template)
        normalized_template = re.sub(r"\s{2,}", " ", normalized_template).strip()
    template_vars: dict[str, Any] = {
        "machine_type": machine_type,
        "device_type": device_type,
    }
    if include_target_credentials and "--user" in normalized_template:
        template_vars["target_username"] = target_username
        template_vars["target_password"] = target_password
    return render_remote_command(normalized_template, remote_path, template_vars)


def probe_remote_package_supports_credentials(client, remote_path: str) -> bool:
    command = f"grep -a -Eq -- '--user|--password' {shlex.quote(remote_path)}"
    result = client.exec_noninteractive_command(command)
    if result["exit_code"] == 0:
        return True
    if result["exit_code"] == 1:
        return False
    raise ApiError(f"检测安装包参数支持情况失败: {result.get('stderr') or result.get('stdout') or '未知错误'}")


def resolve_package_target_credentials(
    session: dict[str, Any],
    device_type: str,
) -> dict[str, Any]:
    """解析部署目标的连接信息，优先使用 SSH 连接中配置的目标信息，回退到机器人身份中的默认信息"""
    normalized_device_type = str(device_type or "ORIN").strip().upper() or "ORIN"
    processor_auth = session.get("processor_auth") or {}
    target_auth = processor_auth.get(normalized_device_type) if isinstance(processor_auth, dict) else {}
    identity = robot_identity(session)
    if not isinstance(target_auth, dict):
        target_auth = {}
    configured_host = str(target_auth.get("host") or "").strip()
    configured_username = str(target_auth.get("username") or "").strip()
    configured_password = str(target_auth.get("password") or "")
    try:
        configured_port = int(target_auth.get("port") or 22)
    except (TypeError, ValueError):
        configured_port = 22
    if normalized_device_type == "ORIN":
        return {
            "device_type": "ORIN",
            "host": configured_host or identity.get("robot_host", ""),
            "port": configured_port or int(identity.get("robot_port") or 22),
            "username": configured_username or str(identity.get("robot_username") or "").strip(),
            "password": configured_password,
            "requires_jump": False,
        }
    if normalized_device_type != "PICO":
        raise ApiError(f"不支持的设备类型: {normalized_device_type}")
    return {
        "device_type": "PICO",
        "host": require_text(configured_host, "请先在 SSH 连接中填写 PICO 主机"),
        "port": configured_port,
        "username": require_text(configured_username, "请先在 SSH 连接中填写 PICO 用户名"),
        "password": configured_password,
        "requires_jump": True,
    }


def create_package_target_client(
    session: dict[str, Any],
    device_type: str,
) -> tuple[Any, bool, dict[str, Any]]:
    base_client = ensure_client_connected(session)
    target = resolve_package_target_credentials(session, device_type)
    if not target["requires_jump"]:
        return base_client, False, target

    jump_client = RobotClient()
    jump_client.connect_via_jump(
        base_client,
        ConnectionConfig(
            host=str(target["host"]),
            port=int(target["port"]),
            username=str(target["username"]),
            password=str(target["password"]),
        ),
    )
    return jump_client, True, target


def resolve_deploy_target(client, file_name: str) -> tuple[str, str, str]:
    """解析部署目标的远程路径，返回远程目录、文件名和完整远程路径"""
    resolved_remote_dir = client.resolve_remote_path(PACKAGE_DEPLOY_DIR)
    normalized_file_name = os.path.basename(require_text(file_name, "文件名不能为空"))
    if not normalized_file_name:
        raise ApiError("文件名不能为空")
    remote_path = client.resolve_remote_path(posixpath.join(resolved_remote_dir, normalized_file_name))
    return resolved_remote_dir, normalized_file_name, remote_path
