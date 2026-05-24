import posixpath
from typing import Any

from ....core.models import TaskFailure
from ....infra.stores import TaskContext
from ....shared.runtime import upload_progress_manager
from ....shared.confirmation import apply_confirmation_response, set_runtime_value
from ....shared import (
    extract_critical_command_warnings,
    log_command_result,
    render_remote_command,
)
from ...services import robot_identity
from ..common import create_package_target_client, find_playbook_step
from ..task_support import build_workflow_status_reporter, log_playbook_steps


def _append_stage_logs(ctx: TaskContext, stage_payload: dict[str, Any], source_metadata: dict[str, Any] | None) -> None:
    if source_metadata and source_metadata.get("source_kind") == "file_server":
        ctx.log(f"文件服务器路径: {source_metadata.get('source_path')}")
        ctx.log(f"裁剪后的下载路径: {source_metadata.get('download_path')}")
        ctx.log(f"已下载到本机临时目录: {source_metadata.get('local_tmp_path')}")
    if bool(stage_payload.get("upload_skipped")):
        ctx.log(
            f"检测到远端同名安装包，跳过上传并直接复用: "
            f"{stage_payload.get('resolved_remote_path') or stage_payload.get('remote_deb_path')}"
        )
        return
    removed_files = stage_payload.get("removed_files") if isinstance(stage_payload.get("removed_files"), list) else []
    if removed_files:
        ctx.log("清理目标目录中同名旧安装包")
        for removed_file in removed_files:
            ctx.log(f"已删除旧包: {removed_file}")
    elif bool(stage_payload.get("cleanup_existing_remote_files")):
        ctx.log("目标目录没有需要清理的同名旧安装包")
    else:
        ctx.log("跳过同名旧安装包清理，直接上传新的安装包")
    ctx.log(f"上传安装包到 {stage_payload.get('resolved_remote_path') or stage_payload.get('remote_deb_path')}")


def _build_playbook_status_reporter(ctx: TaskContext, *, upload_token: str, tool_context: dict[str, Any]) -> Any:
    def progress_transformer(progress_info: dict[str, str], active_tool_context: dict[str, Any]) -> dict[str, str]:
        raw_source_metadata = (active_tool_context or {}).get("source_metadata")
        source_metadata = raw_source_metadata if isinstance(raw_source_metadata, dict) else {}
        if progress_info["step_name"] == "prepare_package_source" and str(source_metadata.get("source_kind") or "").strip() == "file_server":
            progress_info["phase"] = "downloading_from_server"
        return progress_info

    return build_workflow_status_reporter(
        ctx,
        upload_token=upload_token,
        tool_context=tool_context,
        total_bytes_getter=lambda active_tool_context: int((active_tool_context or {}).get("file_size") or 0) or None,
        progress_transformer=progress_transformer,
        log_pending_confirmation=True,
    )


def _build_install_output_callback(
    ctx: TaskContext,
    *,
    upload_token: str,
    tool_context: dict[str, Any],
) -> Any:
    state = {"last_line": ""}

    def callback(line: str) -> None:
        normalized_line = str(line or "").strip()
        if not normalized_line or normalized_line == state["last_line"]:
            return
        state["last_line"] = normalized_line
        ctx.log(f"[install] {normalized_line}")
        total_bytes = int((tool_context or {}).get("file_size") or 0) or None
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=total_bytes,
            total_bytes=total_bytes,
            phase="installing",
            message=normalized_line,
            done=False,
            owner_id="",
        )

    return callback


def create_package_workflow_task_runner(
    session: dict[str, Any],
    *,
    remote_dir: str,
    machine_type: str,
    device_type: str,
    rollback_template: str,
    file_name: str,
    source_metadata: dict[str, Any] | None = None,
    cleanup_existing_remote_files: bool = True,
    upload_token: str = "",
    owner_id: str = "",
):
    identity = robot_identity(session)
    preview_remote_path = posixpath.join(remote_dir, file_name)
    title = f"整包部署 {file_name}"
    if machine_type:
        title = f"整包部署 [{machine_type}/{device_type}] {file_name}"
    else:
        title = f"整包部署 [{device_type}] {file_name}"

    def runner(ctx: TaskContext, continuation: dict[str, Any] | None = None) -> dict[str, Any]:
        client, should_close_target_client, target = create_package_target_client(session, device_type)
        remote_path = client.resolve_remote_path(posixpath.join(remote_dir, file_name))
        resolved_source_metadata = dict(source_metadata or {})
        warnings: list[str] = []
        summary: dict[str, Any] = {
            "remote_deb_path": remote_path,
            "temp_remote_path": remote_path,
            "removed_files": [],
            "install_command": "",
            "rollback_command": "",
            "machine_type": machine_type,
            "device_type": str(target.get("device_type") or device_type),
            "target_host": str(target.get("host") or ""),
            "target_port": int(target.get("port") or 22),
            "target_username": str(target.get("username") or ""),
            "cleanup_existing_remote_files": cleanup_existing_remote_files,
            "source_metadata": resolved_source_metadata,
            "warnings": warnings,
        }
        history = {
            **identity,
            "operation_type": "deployment",
            "title": title,
            "remote_deb_path": remote_path,
            "target_path": remote_path,
            "install_command": "",
            "rollback_command": "",
            "machine_type": machine_type,
            "device_type": str(target.get("device_type") or device_type),
            "cleanup_existing_remote_files": cleanup_existing_remote_files,
        }
        ctx.log(f"目标机器人: {identity['robot_username']}@{identity['robot_host']}:{identity['robot_port']}")
        if machine_type:
            ctx.log(f"目标机型: {machine_type}")
        ctx.log(f"目标处理器: {target.get('device_type')} {target.get('username')}@{target.get('host')}:{target.get('port')}")
        try:
            ctx.log(f"目标远端安装包路径: {remote_path}")

            from ....playbooks import run_scripted_playbook_by_id

            workflow_context = {
                "session": session,
                "session_id": owner_id,
                "remote_deb_path": remote_path,
                "machine_type": machine_type,
                "device_type": str(target.get("device_type") or device_type).upper(),
                "file_name": file_name,
                "cleanup_existing_remote_files": cleanup_existing_remote_files,
                "upload_token": upload_token,
                "source_metadata": resolved_source_metadata,
            }
            set_runtime_value(
                workflow_context,
                "install_output_callback",
                _build_install_output_callback(
                    ctx,
                    upload_token=upload_token,
                    tool_context=workflow_context,
                ),
            )
            resume_state = None
            if isinstance(continuation, dict):
                workflow_context = apply_confirmation_response(
                    workflow_context,
                    continuation.get("pending_confirmation"),
                    str(continuation.get("confirmation_response") or "").strip(),
                )
                raw_resume_state = continuation.get("resume_state")
                resume_state = raw_resume_state if isinstance(raw_resume_state, dict) else None

            playbook_result = run_scripted_playbook_by_id(
                "package-deploy",
                workflow_context,
                workflow_type="normal",
                resume_state=resume_state,
                status_reporter=_build_playbook_status_reporter(
                    ctx,
                    upload_token=upload_token,
                    tool_context=workflow_context,
                ),
            )
            summary["workflow_id"] = "package-deploy"
            summary["workflow_type"] = "normal"
            summary["workflow_result"] = playbook_result or {}
            if isinstance(playbook_result, dict):
                summary["workflow_tree_state"] = playbook_result.get("tree_state")
                summary["workflow_node_states"] = playbook_result.get("node_states") or {}
            history["workflow_id"] = "package-deploy"
            history["workflow_type"] = "normal"
            ctx.log(
                "Workflow 返回: "
                f"type={type(playbook_result).__name__}, "
                f"passed={bool(playbook_result.get('passed')) if isinstance(playbook_result, dict) else 'n/a'}, "
                f"conclusion={str(playbook_result.get('conclusion') or '') if isinstance(playbook_result, dict) else ''}, "
                f"next_action={str(playbook_result.get('next_action') or '') if isinstance(playbook_result, dict) else ''}"
            )
            if not isinstance(playbook_result, dict):
                raise TaskFailure("未找到 normal workflow: package-deploy", {"summary": summary, "history": history})
            if isinstance(playbook_result.get("pending_confirmation"), dict):
                probe_step = (
                    find_playbook_step(playbook_result, "probe_package_options")
                    or find_playbook_step(playbook_result, "probe_package_machine_types")
                    or {}
                )
                probe_payload = probe_step.get("raw_result") if isinstance(probe_step.get("raw_result"), dict) else {}
                if probe_payload:
                    summary["probe_command"] = str(probe_payload.get("command") or "").strip()
                    summary["machine_options"] = probe_payload.get("options") or probe_payload.get("machine_options") or []
                    inferred_machine_type = str(probe_payload.get("inferred_value") or probe_payload.get("inferred_machine_type") or "").strip()
                    if inferred_machine_type:
                        summary["inferred_machine_type"] = inferred_machine_type
                        summary["machine_type"] = inferred_machine_type
                    if str(probe_payload.get("warning") or "").strip():
                        warnings.append(str(probe_payload.get("warning") or "").strip())
                summary["workflow_result"] = playbook_result
                return {
                    "summary": summary,
                    "history": history,
                    "pending_confirmation": playbook_result.get("pending_confirmation"),
                    "resume_state": playbook_result.get("resume_state"),
                }

            log_playbook_steps(ctx, playbook_result)

            stage_step = find_playbook_step(playbook_result, "stage_package_to_remote_target") or {}
            stage_payload = stage_step.get("raw_result") if isinstance(stage_step.get("raw_result"), dict) else {}
            if stage_payload:
                summary["removed_files"] = stage_payload.get("removed_files") or []
                summary["upload_skipped"] = bool(stage_payload.get("upload_skipped"))
                summary["cleanup_existing_remote_files"] = bool(stage_payload.get("cleanup_existing_remote_files"))
                resolved_stage_remote_path = str(stage_payload.get("resolved_remote_path") or "").strip()
                if resolved_stage_remote_path:
                    summary["remote_deb_path"] = resolved_stage_remote_path
                    summary["temp_remote_path"] = resolved_stage_remote_path
                    history["remote_deb_path"] = resolved_stage_remote_path
                    history["target_path"] = resolved_stage_remote_path
                    session["last_remote_deb_path"] = resolved_stage_remote_path
                prepared_source_metadata = workflow_context.get("source_metadata") if isinstance(workflow_context.get("source_metadata"), dict) else resolved_source_metadata
                summary["source_metadata"] = prepared_source_metadata
                _append_stage_logs(ctx, stage_payload, prepared_source_metadata)
                if not bool(stage_payload.get("upload_skipped")):
                    ctx.log("安装包上传完成")

            install_step = find_playbook_step(playbook_result, "install_package_on_selected_robot_type") or {}
            install_payload = install_step.get("raw_result") if isinstance(install_step.get("raw_result"), dict) else {}
            install_result = install_payload.get("result") if isinstance(install_payload.get("result"), dict) else {}
            install_command = str(install_payload.get("command") or "").strip()
            if install_command:
                summary["install_command"] = install_command
                history["install_command"] = install_command
            if install_result:
                summary["install_result"] = install_result
                log_command_result(ctx, "安装命令", install_result)
                install_output_text = "\n".join(
                    part
                    for part in [str(install_result.get("stdout") or "").strip(), str(install_result.get("stderr") or "").strip()]
                    if part
                )
                if "Deployment finished successfully" in install_output_text:
                    ctx.log("安装命令输出命中成功标记: Deployment finished successfully")
                if "Update Version Success" in install_output_text:
                    ctx.log("安装命令输出命中成功标记: Update Version Success")
                install_warnings = extract_critical_command_warnings("安装命令", install_result)
                warnings.extend(install_warnings)
                for warning in install_warnings:
                    ctx.log(f"告警: {warning}")
            if "supports_target_credentials" in install_payload:
                summary["supports_target_credentials"] = bool(install_payload.get("supports_target_credentials"))
                history["supports_target_credentials"] = bool(install_payload.get("supports_target_credentials"))

            probe_step = (
                find_playbook_step(playbook_result, "probe_package_options")
                or find_playbook_step(playbook_result, "probe_package_machine_types")
                or {}
            )
            probe_payload = probe_step.get("raw_result") if isinstance(probe_step.get("raw_result"), dict) else {}
            if probe_payload:
                summary["probe_command"] = str(probe_payload.get("command") or "").strip()
                summary["machine_options"] = probe_payload.get("options") or probe_payload.get("machine_options") or []
                if str(probe_payload.get("warning") or "").strip():
                    warnings.append(str(probe_payload.get("warning") or "").strip())
                    ctx.log(f"告警: {str(probe_payload.get('warning') or '').strip()}")

            if rollback_template:
                resolved_rollback_command = render_remote_command(
                    rollback_template,
                    remote_path,
                    {
                        "machine_type": machine_type,
                        "device_type": str(target.get("device_type") or device_type),
                        "target_username": str(target.get("username") or ""),
                        "target_password": str(target.get("password") or ""),
                    },
                )
                summary["rollback_command"] = resolved_rollback_command
                history["rollback_command"] = resolved_rollback_command

            if not bool(playbook_result.get("passed")):
                ctx.log(
                    "Workflow 判定未通过，准备标记任务失败: "
                    f"conclusion={str(playbook_result.get('conclusion') or '')}, "
                    f"next_action={str(playbook_result.get('next_action') or '')}"
                )
                raise TaskFailure(
                    str(playbook_result.get("conclusion") or playbook_result.get("next_action") or "部署 workflow 执行失败"),
                    {"summary": summary, "history": history},
                )
            ctx.log(f"Workflow 判定通过，准备返回任务结果；warnings={len(warnings)}")
            ctx.log("部署任务执行完成")
            return {"summary": summary, "history": history}
        finally:
            if should_close_target_client:
                client.close()

    return title, {"remote_deb_path": preview_remote_path, "file_name": file_name, "upload_token": upload_token}, runner


create_package_deploy_task_runner = create_package_workflow_task_runner
create_deploy_runner = create_package_workflow_task_runner
