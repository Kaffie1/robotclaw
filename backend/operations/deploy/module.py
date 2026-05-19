import posixpath
from typing import Any

from ...core.models import TaskFailure
from ...infra.stores import TaskContext
from ...shared.runtime import upload_progress_manager
from ...common import log_command_result
from ..services import current_robot_password, ensure_client_connected, robot_identity


def _find_playbook_step(playbook_result: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("tool_name") or "").strip() == tool_name:
            return step
    return None


def _log_playbook_steps(ctx: TaskContext, playbook_result: dict[str, Any]) -> None:
    playbook_title = str(playbook_result.get("playbook_title") or playbook_result.get("playbook_id") or "workflow").strip()
    ctx.log(f"开始执行 workflow: {playbook_title}")
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = str(step.get("name") or step.get("tool_name") or "step").strip()
        status_text = "成功" if bool(step.get("passed")) else "失败"
        ctx.log(f"Workflow 步骤[{status_text}]: {step_name}")
    conclusion = str(playbook_result.get("conclusion") or "").strip()
    if conclusion:
        ctx.log(f"Workflow 结论: {conclusion}")


def _build_module_playbook_status_reporter(
    ctx: TaskContext,
    *,
    upload_token: str,
    tool_context: dict[str, Any],
) -> Any:
    state = {"last_path": "", "last_message": ""}

    def resolve_phase(message: str) -> str:
        if "准备模块安装包来源" in message:
            return "downloading_from_server"
        if "替换自动部署模块资源" in message:
            return "preparing"
        if "上传模块安装包" in message:
            return "uploading_to_robot"
        if "执行模块安装" in message or "启动模块" in message or "检查模块健康状态" in message:
            return "installing"
        return "installing"

    def reporter(
        _: dict[str, Any],
        pending_confirmation: dict[str, Any] | None,
        active_node_path: str,
        active_node_message: str,
    ) -> None:
        if isinstance(pending_confirmation, dict):
            return
        message = str(active_node_message or "").strip()
        node_path = str(active_node_path or "").strip()
        if not message:
            return
        if node_path == state["last_path"] and message == state["last_message"]:
            return
        state["last_path"] = node_path
        state["last_message"] = message
        ctx.log(f"Workflow 执行中: {message}")
        progress_phase = resolve_phase(message)
        package_files = (tool_context or {}).get("package_files")
        total_bytes = 0
        if isinstance(package_files, list):
            total_bytes = sum(len(item.get("package_file_bytes") or b"") for item in package_files if isinstance(item, dict))
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=total_bytes if progress_phase == "installing" else None,
            total_bytes=total_bytes if total_bytes > 0 else None,
            phase=progress_phase,
            message=message,
            done=False,
            owner_id="",
        )

    return reporter


def _first_failed_message(playbook_result: dict[str, Any]) -> str:
    for step in playbook_result.get("steps") or []:
        if isinstance(step, dict) and not bool(step.get("passed")):
            return str(step.get("failure_message") or step.get("output") or step.get("name") or "workflow 执行失败").strip()
    return str(playbook_result.get("conclusion") or playbook_result.get("next_action") or "workflow 执行失败").strip()


def create_module_deploy_runner(
    session: dict[str, Any],
    *,
    module_name: str,
    module_path: str,
    package_sources: list[dict[str, Any]],
    auto_deploy_version: str = "",
    upload_token: str,
    install_template: str,
    up_wait_seconds: int = 10,
    start_command: str,
    health_command: str,
    rollback_template: str,
    auto_rollback: bool,
    auto_deploy: bool = False,
    owner_id: str = "",
):
    client = ensure_client_connected(session)
    identity = robot_identity(session)
    sudo_password = current_robot_password(session)
    package_file_names = [
        str(item.get("package_file_name") or "").strip()
        for item in package_sources
        if isinstance(item, dict) and str(item.get("package_file_name") or "").strip()
    ]
    package_title = package_file_names[0] if len(package_file_names) == 1 else f"{len(package_sources)} 个包"
    title = f"模块部署 [{module_name}] {package_title}"

    def runner(ctx: TaskContext, continuation: dict[str, Any] | None = None) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "module_name": module_name,
            "module_path": module_path,
            "compose_profiles": "",
            "up_wait_seconds": max(int(up_wait_seconds or 0), 0),
            "package_file_name": package_file_names[0] if package_file_names else "",
            "package_files": [],
            "removed_files": [],
            "uploaded_file_paths": [],
            "uploaded_file_path": "",
            "skipped_existing_files": [],
            "install_command": "",
            "start_command": start_command,
            "health_command": health_command,
            "rollback_command": "",
            "auto_deploy_version": auto_deploy_version,
            "warnings": [],
        }
        history = {
            **identity,
            "operation_type": "deployment",
            "title": title,
            "target_path": module_path,
            "remote_deb_path": "",
            "remote_deb_paths": [],
            "install_command": "",
            "start_command": start_command,
            "health_command": health_command,
            "rollback_command": "",
            "module_name": module_name,
            "module_path": module_path,
            "compose_profiles": "",
        }
        ctx.log(f"目标机器人: {identity['robot_username']}@{identity['robot_host']}:{identity['robot_port']}")
        ctx.log(f"目标模块: {module_name}")
        ctx.log(f"模块目录: {module_path}")
        if not client.path_exists(module_path):
            raise TaskFailure(f"模块目录不存在: {module_path}", {"summary": summary, "history": history})
        if not client.is_dir_path(module_path):
            raise TaskFailure(f"模块路径不是目录: {module_path}", {"summary": summary, "history": history})
        ctx.log(f"自动读取 COMPOSE_PROFILES: {client.get_interactive_env('COMPOSE_PROFILES') or '(空)'}")
        workflow_context = {
            "session": session,
            "session_id": owner_id,
            "module_name": module_name,
            "module_path": module_path,
            "package_sources": package_sources,
            "upload_token": upload_token,
            "auto_deploy": bool(auto_deploy),
            "auto_deploy_version": str(auto_deploy_version or "").strip(),
            "install_template": install_template,
            "up_wait_seconds": max(int(up_wait_seconds or 0), 0),
            "start_command": start_command,
            "health_command": health_command,
            "rollback_template": rollback_template,
            "auto_rollback": bool(auto_rollback),
            "sudo_password": sudo_password,
        }
        try:
            from ...playbooks import run_scripted_playbook_by_id

            playbook_result = run_scripted_playbook_by_id(
                "module-deploy",
                workflow_context,
                workflow_type="normal",
                status_reporter=_build_module_playbook_status_reporter(
                    ctx,
                    upload_token=upload_token,
                    tool_context=workflow_context,
                ),
            )
            summary["workflow_id"] = "module-deploy"
            summary["workflow_type"] = "normal"
            summary["workflow_result"] = playbook_result or {}
            history["workflow_id"] = "module-deploy"
            history["workflow_type"] = "normal"
            if not isinstance(playbook_result, dict):
                raise TaskFailure("未找到 normal workflow: module-deploy", {"summary": summary, "history": history})
            _log_playbook_steps(ctx, playbook_result)
            if not bool(playbook_result.get("passed")):
                raise TaskFailure(_first_failed_message(playbook_result), {"summary": summary, "history": history})

            replace_step = _find_playbook_step(playbook_result, "module_replace_remote_assets") or {}
            replace_payload = replace_step.get("raw_result") if isinstance(replace_step.get("raw_result"), dict) else {}
            if replace_payload:
                summary["auto_deploy_version"] = str(replace_payload.get("auto_deploy_version") or summary["auto_deploy_version"])
                summary["project_root"] = str(replace_payload.get("project_root") or "")
                summary["replaced_paths"] = list(replace_payload.get("replaced_paths") or [])
                summary["local_module_assets"] = replace_payload.get("local_module_assets") or {}
                if replace_payload.get("result"):
                    log_command_result(ctx, "替换 docker-compose.yaml", replace_payload.get("result"))

            stage_step = _find_playbook_step(playbook_result, "module_stage_packages") or {}
            stage_payload = stage_step.get("raw_result") if isinstance(stage_step.get("raw_result"), dict) else {}
            if stage_payload:
                summary["package_files"] = list(stage_payload.get("package_files") or [])
                summary["removed_files"] = list(stage_payload.get("removed_files") or [])
                summary["uploaded_file_paths"] = list(stage_payload.get("uploaded_file_paths") or [])
                summary["uploaded_file_path"] = str(stage_payload.get("uploaded_file_path") or "")
                summary["skipped_existing_files"] = list(stage_payload.get("skipped_existing_files") or [])
                for package_item in summary["package_files"]:
                    if not isinstance(package_item, dict):
                        continue
                    for removed_file in package_item.get("removed_files") or []:
                        ctx.log(f"已删除旧包: {removed_file}")
                    move_result = package_item.get("move_result")
                    if isinstance(move_result, dict):
                        log_command_result(ctx, f"移动安装包命令 [{package_item.get('package_file_name') or ''}]", move_result)
                history["remote_deb_paths"] = list(summary["uploaded_file_paths"])
                history["remote_deb_path"] = str(summary["uploaded_file_path"] or "")

            install_step = _find_playbook_step(playbook_result, "module_install") or {}
            install_payload = install_step.get("raw_result") if isinstance(install_step.get("raw_result"), dict) else {}
            install_result = install_payload.get("result") if isinstance(install_payload.get("result"), dict) else {}
            if install_payload:
                summary["compose_profiles"] = str(install_payload.get("compose_profiles") or "")
                summary["install_command"] = str(install_payload.get("install_command") or "")
                history["compose_profiles"] = summary["compose_profiles"]
                history["install_command"] = summary["install_command"]
            if install_result:
                summary["install_result"] = install_result
                log_command_result(ctx, "模块安装命令", install_result)

            start_step = _find_playbook_step(playbook_result, "module_start") or {}
            start_payload = start_step.get("raw_result") if isinstance(start_step.get("raw_result"), dict) else {}
            start_result = start_payload.get("result") if isinstance(start_payload.get("result"), dict) else {}
            if start_result and not bool(start_payload.get("skipped")):
                summary["start_result"] = start_result
                log_command_result(ctx, "启动命令", start_result)

            health_step = _find_playbook_step(playbook_result, "module_health_check") or {}
            health_payload = health_step.get("raw_result") if isinstance(health_step.get("raw_result"), dict) else {}
            health_result = health_payload.get("result") if isinstance(health_payload.get("result"), dict) else {}
            rollback_result = health_payload.get("rollback_result") if isinstance(health_payload.get("rollback_result"), dict) else {}
            if str(health_payload.get("rollback_command") or "").strip():
                summary["rollback_command"] = str(health_payload.get("rollback_command") or "")
                history["rollback_command"] = summary["rollback_command"]
            if health_result and not bool(health_payload.get("skipped")):
                summary["health_result"] = health_result
                log_command_result(ctx, "健康检查", health_result)
            if rollback_result:
                summary["rollback_result"] = rollback_result
                log_command_result(ctx, "自动回滚", rollback_result)
                if int(health_result.get("exit_code") or 0) != 0 and int(rollback_result.get("exit_code") or 0) == 0:
                    warning = "健康检查失败，已自动回滚到可用状态"
                    summary["warnings"].append(warning)
                    ctx.log(f"告警: {warning}")

            ctx.log("模块部署任务执行完成")
            return {"summary": summary, "history": history}
        except TaskFailure:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TaskFailure(str(exc), {"summary": summary, "history": history}) from exc

    return title, {"module_name": module_name, "module_path": module_path, "upload_token": upload_token}, runner
