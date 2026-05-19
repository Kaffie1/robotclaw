import posixpath
from typing import Any

from ...core.models import TaskFailure
from ...infra.stores import TaskContext
from ...shared.runtime import upload_progress_manager
from ...shared.confirmation import apply_confirmation_response
from ...common import (
    detect_ignored_package_install_error,
    extract_critical_command_warnings,
    log_command_result,
    render_remote_command,
)
from ..services import robot_identity
from .common import create_package_target_client


def _find_playbook_step(playbook_result: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    """在 workflow 的执行结果中查找指定工具的步骤，返回该步骤的原始结果"""
    for step in playbook_result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("tool_name") or "").strip() == tool_name:
            return step
    return None


def _log_playbook_steps(ctx: TaskContext, playbook_result: dict[str, Any]) -> None:
    """将 workflow 的每个步骤的状态和消息都记录到任务日志中，方便用户查看和排查问题"""
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


def _build_playbook_status_reporter(
    ctx: TaskContext,
    *,
    upload_token: str,
    tool_context: dict[str, Any],
) -> Any:
    """构建一个 workflow 状态报告函数，用于将 workflow 的当前阶段和消息实时更新到上传进度中"""
    state = {"last_path": "", "last_message": ""}

    def resolve_phase(message: str) -> str:
        if "准备部署安装包来源" in message:
            raw_source_metadata = (tool_context or {}).get("source_metadata")
            source_metadata = raw_source_metadata if isinstance(raw_source_metadata, dict) else {}
            source_kind = str(source_metadata.get("source_kind") or "").strip()
            return "downloading_from_server" if source_kind == "file_server" else "preparing"
        if "准备远端安装包" in message:
            return "uploading_to_robot"
        if "检查安装包是否存在" in message:
            return "preparing"
        if "识别整包支持的机型" in message:
            return "probing_machine_type"
        if "修复安装包执行权限" in message:
            return "installing"
        if "执行整包安装" in message:
            return "installing"
        if "检查部署健康状态" in message:
            return "installing"
        return "installing"

    def reporter(
        _: dict[str, Any],
        pending_confirmation: dict[str, Any] | None,
        active_node_path: str,
        active_node_message: str,
    ) -> None:
        message = str(active_node_message or "").strip()
        node_path = str(active_node_path or "").strip()
        if isinstance(pending_confirmation, dict):
            pending_message = str(pending_confirmation.get("message") or "").strip()
            if pending_message and pending_message != state["last_message"]:
                ctx.log(f"Workflow 等待确认: {pending_message}")
                state["last_message"] = pending_message
            return
        if not message:
            return
        if node_path == state["last_path"] and message == state["last_message"]:
            return
        state["last_path"] = node_path
        state["last_message"] = message
        ctx.log(f"Workflow 执行中: {message}")
        total_bytes = len((tool_context or {}).get("file_bytes") or b"")
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=total_bytes if resolve_phase(message) == "installing" else None,
            total_bytes=total_bytes,
            phase=resolve_phase(message),
            message=message,
            done=False,
            owner_id="",
        )

    return reporter


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
        total_bytes = len((tool_context or {}).get("file_bytes") or b"")
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


def create_deploy_runner(
    session: dict[str, Any],
    *,
    remote_dir: str,
    machine_type: str,
    device_type: str,
    install_template: str,
    start_command: str,
    health_command: str,
    rollback_template: str,
    auto_rollback: bool,
    file_name: str,
    source_metadata: dict[str, Any] | None = None,
    cleanup_existing_remote_files: bool = True,
    probe_command_template: str = "",
    fallback_machine_options: list[dict[str, str]] | None = None,
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
            "start_command": start_command,
            "health_command": health_command,
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
            "start_command": start_command,
            "health_command": health_command,
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

            from ...playbooks import run_scripted_playbook_by_id

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
                "install_template": install_template,
                "probe_command_template": probe_command_template,
                "fallback_machine_options": list(fallback_machine_options or []),
                "health_command": health_command,
            }
            workflow_context["install_output_callback"] = _build_install_output_callback(
                ctx,
                upload_token=upload_token,
                tool_context=workflow_context,
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
                summary["workflow_result"] = playbook_result
                return {
                    "summary": summary,
                    "history": history,
                    "pending_confirmation": playbook_result.get("pending_confirmation"),
                    "resume_state": playbook_result.get("resume_state"),
                }

            _log_playbook_steps(ctx, playbook_result)

            stage_step = _find_playbook_step(playbook_result, "package_stage_remote") or {}
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

            install_step = _find_playbook_step(playbook_result, "package_install") or {}
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
                if int(install_result.get("exit_code") or 0) != 0:
                    ignored_error = detect_ignored_package_install_error(install_result)
                    if ignored_error:
                        warnings.append(ignored_error)
                        ctx.log(f"告警: {ignored_error}")
                install_warnings = extract_critical_command_warnings("安装命令", install_result)
                warnings.extend(install_warnings)
                for warning in install_warnings:
                    ctx.log(f"告警: {warning}")
            if "supports_target_credentials" in install_payload:
                summary["supports_target_credentials"] = bool(install_payload.get("supports_target_credentials"))
                history["supports_target_credentials"] = bool(install_payload.get("supports_target_credentials"))

            probe_step = _find_playbook_step(playbook_result, "package_probe_machine_types") or {}
            probe_payload = probe_step.get("raw_result") if isinstance(probe_step.get("raw_result"), dict) else {}
            if probe_payload:
                summary["probe_command"] = str(probe_payload.get("command") or "").strip()
                summary["machine_options"] = probe_payload.get("machine_options") or []
                if str(probe_payload.get("warning") or "").strip():
                    warnings.append(str(probe_payload.get("warning") or "").strip())
                    ctx.log(f"告警: {str(probe_payload.get('warning') or '').strip()}")

            health_step = _find_playbook_step(playbook_result, "remote_execute_readonly") or {}
            health_payload = health_step.get("raw_result") if isinstance(health_step.get("raw_result"), dict) else {}
            health_result = health_payload.get("result") if isinstance(health_payload.get("result"), dict) else {}
            if health_result:
                summary["health_result"] = health_result
                log_command_result(ctx, "健康检查", health_result)

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
