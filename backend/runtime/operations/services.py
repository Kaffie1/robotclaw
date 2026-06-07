import posixpath
from typing import Any

from backend.core.models import ApiError, TaskFailure
from backend.runtime.tasks import TaskContext
from backend.infra.container import history_store, session_store
from backend.core.time import now_text
from backend.core.shared import log_command_result, require_text


def ensure_client_connected(session: dict[str, Any]):
    client = session_store.get_client(session)
    client.ensure_connected()
    return client


def robot_identity(session: dict[str, Any]) -> dict[str, Any]:
    config = session_store.get_last_config(session)
    return {
        "robot_host": config.get("host", ""),
        "robot_port": config.get("port"),
        "robot_username": config.get("username", ""),
    }


def current_robot_password(session: dict[str, Any]) -> str:
    orin_auth = resolve_processor_auth_target(session, "ORIN")
    if isinstance(orin_auth, dict) and str(orin_auth.get("password") or ""):
        return str(orin_auth.get("password") or "")
    ssh_auth = session_store.get_ssh_auth(session)
    if isinstance(ssh_auth, dict):
        return str(ssh_auth.get("password") or "")
    return ""


def resolve_processor_auth_target(session: dict[str, Any], device_type: str) -> dict[str, Any]:
    normalized_device_type = str(device_type or "ORIN").strip().upper() or "ORIN"
    processor_auth = session_store.get_processor_auth(session)
    target_auth = processor_auth.get(normalized_device_type) if isinstance(processor_auth, dict) else {}
    return target_auth if isinstance(target_auth, dict) else {}


def ensure_connected_to_history_target(session: dict[str, Any], entry: dict[str, Any]):
    client = ensure_client_connected(session)
    config = session_store.get_last_config(session)
    if (
        str(config.get("host", "")) != str(entry.get("robot_host", ""))
        or int(config.get("port", 0)) != int(entry.get("robot_port", 0) or 0)
        or str(config.get("username", "")) != str(entry.get("robot_username", ""))
    ):
        raise ApiError("请先连接到该历史记录对应的机器人，再执行回滚")
    return client


def refresh_remote_shortcuts(session: dict[str, Any]) -> dict[str, Any]:
    client = ensure_client_connected(session)
    shortcut_payload = client.directory_shortcuts()
    session_store.set_remote_shortcuts(
        session,
        shortcuts=shortcut_payload["shortcuts"],
        preferred_root=shortcut_payload["preferred_root"],
    )
    return shortcut_payload


def create_history_rollback_runner(session: dict[str, Any], entry: dict[str, Any]):
    client = ensure_connected_to_history_target(session, entry)
    identity = {
        "robot_host": entry["robot_host"],
        "robot_port": entry["robot_port"],
        "robot_username": entry["robot_username"],
    }
    if entry["operation_type"] == "deployment":
        rollback_command = require_text(entry.get("rollback_command"), "该部署记录没有保存回滚命令")
        health_command = str(entry.get("health_command") or "").strip()
        title = f"回滚部署 #{entry['id']}"

        def runner(ctx: TaskContext) -> dict[str, Any]:
            summary = {"source_history_id": entry["id"], "rollback_command": rollback_command, "health_command": health_command}
            history = {
                **identity,
                "operation_type": "rollback",
                "title": title,
                "remote_deb_path": entry.get("remote_deb_path", ""),
                "target_path": entry.get("target_path", ""),
                "rollback_command": rollback_command,
                "health_command": health_command,
            }
            ctx.log(f"执行部署回滚命令: {rollback_command}")
            command_result = client.exec_noninteractive_command(rollback_command)
            summary["command_result"] = command_result
            log_command_result(ctx, "部署回滚命令", command_result)
            if command_result["exit_code"] != 0:
                raise TaskFailure("部署回滚失败", {"summary": summary, "history": history})
            if health_command:
                ctx.log(f"执行回滚后的健康检查: {health_command}")
                health_result = client.exec_noninteractive_command(health_command)
                summary["health_result"] = health_result
                log_command_result(ctx, "回滚后健康检查", health_result)
                if health_result["exit_code"] != 0:
                    raise TaskFailure("回滚后的健康检查失败", {"summary": summary, "history": history})
            ctx.log("部署回滚完成")
            return {"summary": summary, "history": history}

        return title, runner
    if entry["operation_type"] == "file_replace":
        backup_path = require_text(entry.get("backup_path"), "该文件替换记录没有可用备份")
        target_path = require_text(entry.get("target_path"), "缺少文件目标路径")
        title = f"恢复文件 {posixpath.basename(target_path)}"

        def runner(ctx: TaskContext) -> dict[str, Any]:
            summary = {"source_history_id": entry["id"], "backup_path": backup_path, "target_path": target_path}
            history = {**identity, "operation_type": "rollback", "title": title, "target_path": target_path, "backup_path": backup_path}
            ctx.log(f"恢复远程文件: {backup_path} -> {target_path}")
            command_result = client.restore_backup(backup_path, target_path)
            summary["command_result"] = command_result
            log_command_result(ctx, "恢复文件命令", command_result)
            ctx.log("文件恢复完成")
            return {"summary": summary, "history": history}

        return title, runner
    raise ApiError("该操作类型暂不支持回滚")


def build_file_replace_history(session: dict[str, Any], remote_path: str, backup_path: str | None, result: dict[str, Any]) -> int:
    entry = {
        "owner_id": session_store.get_session_id(session),
        **robot_identity(session),
        "operation_type": "file_replace",
        "title": f"替换文件 {posixpath.basename(remote_path)}",
        "target_path": remote_path,
        "backup_path": backup_path or "",
        "status": "succeeded",
        "result": result,
        "logs": [f"目标文件: {remote_path}", f"备份路径: {backup_path or '无'}"],
        "created_at": now_text(),
        "finished_at": now_text(),
    }
    return history_store.insert_entry(entry)
