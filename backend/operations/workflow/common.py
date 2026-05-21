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


def find_playbook_step(playbook_result: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    """按 workflow step.name 优先查找步骤，兼容旧数据回退到 tool_name。"""
    normalized_step_name = str(step_name or "").strip()
    if not normalized_step_name:
        return None
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("name") or "").strip() == normalized_step_name:
            return step
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("tool_name") or "").strip() == normalized_step_name:
            return step
    return None


def resolve_playbook_progress(
    execution_snapshot: dict[str, Any],
) -> dict[str, str]:
    """从 workflow 定义中解析当前任务进度，避免在 runner 里硬编码状态映射。"""
    playbook = execution_snapshot.get("matched_context") if isinstance(execution_snapshot, dict) else {}
    task_progress = playbook.get("task_progress") if isinstance(playbook, dict) and isinstance(playbook.get("task_progress"), dict) else {}
    pending_confirmation = execution_snapshot.get("pending_confirmation") if isinstance(execution_snapshot, dict) else None
    active_node_path = str((execution_snapshot or {}).get("active_node_path") or "").strip()
    active_node_message = str((execution_snapshot or {}).get("active_node_message") or "").strip()
    default_phase = str(task_progress.get("default_phase") or "preparing").strip() or "preparing"
    progress = {
        "phase": default_phase,
        "message": active_node_message,
        "step_name": "",
        "step_label": "",
    }

    node_spec = _find_playbook_node_by_path(playbook, active_node_path)
    if isinstance(node_spec, dict):
        progress["step_name"] = str(node_spec.get("name") or node_spec.get("tool_name") or "").strip()
        progress["step_label"] = str(
            node_spec.get("display_name")
            or node_spec.get("message")
            or node_spec.get("name")
            or node_spec.get("tool_name")
            or ""
        ).strip()
        node_progress = node_spec.get("progress") if isinstance(node_spec.get("progress"), dict) else {}
        if node_progress:
            progress["phase"] = str(node_progress.get("phase") or progress["phase"]).strip() or progress["phase"]
            progress["message"] = str(node_progress.get("message") or progress["message"]).strip() or progress["message"]

    if isinstance(pending_confirmation, dict):
        confirmation = pending_confirmation.get("confirmation") if isinstance(pending_confirmation.get("confirmation"), dict) else {}
        confirmation_progress = confirmation.get("progress") if isinstance(confirmation.get("progress"), dict) else {}
        progress["phase"] = str(
            confirmation_progress.get("phase")
            or task_progress.get("waiting_confirmation_phase")
            or "waiting_confirmation"
        ).strip() or "waiting_confirmation"
        progress["message"] = str(
            confirmation_progress.get("message")
            or pending_confirmation.get("message")
            or progress["message"]
        ).strip()
        progress["step_name"] = str(
            pending_confirmation.get("node_name")
            or progress["step_name"]
        ).strip()
        progress["step_label"] = str(
            progress["step_label"]
            or pending_confirmation.get("node_name")
            or pending_confirmation.get("message")
            or ""
        ).strip()
    return progress


def _find_playbook_node_by_path(playbook: dict[str, Any], node_path: str) -> dict[str, Any] | None:
    if not isinstance(playbook, dict):
        return None
    root = playbook.get("root")
    if not isinstance(root, dict):
        return None
    normalized_path = str(node_path or "").strip()
    if not normalized_path or normalized_path == "root":
        return root
    if not normalized_path.startswith("root"):
        return None
    current: dict[str, Any] | None = root
    for match in re.finditer(r"\.children\[(\d+)\]", normalized_path):
        if not isinstance(current, dict):
            return None
        children = current.get("children")
        if not isinstance(children, list):
            return None
        index = int(match.group(1))
        if index < 0 or index >= len(children):
            return None
        child = children[index]
        if not isinstance(child, dict):
            return None
        current = child
    return current
