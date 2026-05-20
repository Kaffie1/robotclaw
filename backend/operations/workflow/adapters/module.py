import posixpath
from typing import Any

from ....core.models import TaskFailure
from ....common import log_command_result
from ...services import current_robot_password, ensure_client_connected, robot_identity
from ....infra.stores import TaskContext
from ..common import find_playbook_step
from ..task_support import build_workflow_status_reporter, first_failed_message, log_playbook_steps


def _build_module_playbook_status_reporter(ctx: TaskContext, *, upload_token: str, tool_context: dict[str, Any]) -> Any:
    def progress_transformer(progress_info: dict[str, str], active_tool_context: dict[str, Any]) -> dict[str, str]:
        package_sources = (active_tool_context or {}).get("package_sources")
        if progress_info["step_name"] == "prepare_module_packages" and any(
            isinstance(item, dict) and str(item.get("source_kind") or "").strip() == "file_server"
            for item in (package_sources if isinstance(package_sources, list) else [])
        ):
            progress_info["phase"] = "downloading_from_server"
        return progress_info

    def total_bytes_getter(active_tool_context: dict[str, Any]) -> int | None:
        package_files = (active_tool_context or {}).get("package_files")
        if not isinstance(package_files, list):
            return None
        return sum(len(item.get("package_file_bytes") or b"") for item in package_files if isinstance(item, dict))

    return build_workflow_status_reporter(
        ctx,
        upload_token=upload_token,
        tool_context=tool_context,
        total_bytes_getter=total_bytes_getter,
        progress_transformer=progress_transformer,
        log_pending_confirmation=False,
    )


def create_module_workflow_task_runner(
    session: dict[str, Any],
    *,
    module_name: str,
    module_path: str,
    package_sources: list[dict[str, Any]],
    auto_deploy_version: str = "",
    upload_token: str,
    up_wait_seconds: int = 10,
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
            "up_wait_seconds": max(int(up_wait_seconds or 0), 0),
            "sudo_password": sudo_password,
        }
        try:
            from ....playbooks import run_scripted_playbook_by_id

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
            log_playbook_steps(ctx, playbook_result)
            if not bool(playbook_result.get("passed")):
                raise TaskFailure(first_failed_message(playbook_result), {"summary": summary, "history": history})

            replace_step = find_playbook_step(playbook_result, "replace_remote_module_assets") or {}
            replace_payload = replace_step.get("raw_result") if isinstance(replace_step.get("raw_result"), dict) else {}
            if replace_payload:
                summary["auto_deploy_version"] = str(replace_payload.get("auto_deploy_version") or summary["auto_deploy_version"])
                summary["project_root"] = str(replace_payload.get("project_root") or "")
                summary["replaced_paths"] = list(replace_payload.get("replaced_paths") or [])
                summary["local_module_assets"] = replace_payload.get("local_module_assets") or {}
                if replace_payload.get("result"):
                    log_command_result(ctx, "替换 docker-compose.yaml", replace_payload.get("result"))

            stage_step = find_playbook_step(playbook_result, "stage_module_packages") or {}
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

            down_step = find_playbook_step(playbook_result, "docker_compose_down_module") or {}
            down_payload = down_step.get("raw_result") if isinstance(down_step.get("raw_result"), dict) else {}
            down_result = down_payload.get("result") if isinstance(down_payload.get("result"), dict) else {}
            if down_payload:
                summary["compose_profiles"] = str(down_payload.get("compose_profiles") or summary["compose_profiles"])
                summary["down_command"] = str(down_payload.get("command") or "")
                history["compose_profiles"] = summary["compose_profiles"]
            if down_result:
                summary["down_result"] = down_result
                log_command_result(ctx, "停止模块容器", down_result)

            up_step = find_playbook_step(playbook_result, "docker_compose_up_module") or {}
            up_payload = up_step.get("raw_result") if isinstance(up_step.get("raw_result"), dict) else {}
            up_result = up_payload.get("result") if isinstance(up_payload.get("result"), dict) else {}
            if up_payload:
                summary["compose_profiles"] = str(up_payload.get("compose_profiles") or summary["compose_profiles"])
                summary["install_command"] = str(up_payload.get("command") or "")
                summary["up_command"] = str(up_payload.get("command") or "")
                history["compose_profiles"] = summary["compose_profiles"]
                history["install_command"] = summary["install_command"]
            if up_result:
                summary["install_result"] = up_result
                summary["up_result"] = up_result
                log_command_result(ctx, "启动模块容器", up_result)

            ctx.log("模块部署任务执行完成")
            return {"summary": summary, "history": history}
        except TaskFailure:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TaskFailure(str(exc), {"summary": summary, "history": history}) from exc

    return title, {"module_name": module_name, "module_path": module_path, "upload_token": upload_token}, runner


create_module_deploy_task_runner = create_module_workflow_task_runner
create_module_deploy_runner = create_module_workflow_task_runner
