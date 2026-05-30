import io
import os
import zipfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from ...core.models import ExecutePayload, ToolCallPayload, ApiError
from ...runtime.operations.services import build_file_replace_history, current_robot_password, ensure_client_connected
from ...runtime.operations.workflow import create_package_target_client
from ...core.validation import parse_bool, require_text, require_upload
from ...infra.container import upload_progress_manager
from ...runtime.tools import tool_registry
from ..support import build_log_archive_name, collect_log_files, get_session, get_session_id

router = APIRouter()


@router.get("/api/upload-progress/{upload_token}")
def api_upload_progress(upload_token: str, request: Request):
    return {"ok": True, "progress": upload_progress_manager.get(upload_token, get_session_id(request))}


@router.post("/api/execute")
def api_execute(payload: ExecutePayload, request: Request):
    result = tool_registry.call_tool(
        "remote_execute_readonly",
        payload.model_dump(),
        {"session_id": get_session_id(request)},
    )
    return {
        "ok": True,
        "result": result["result"],
        "command": result["command"],
        "interactive": result["interactive"],
        "device_type": result["device_type"],
    }


@router.get("/api/list-dir")
def api_list_dir(request: Request, path: str = "/", device_type: str = "ORIN"):
    result = tool_registry.call_tool(
        "remote_list_dir",
        {"path": path, "device_type": device_type},
        {"session_id": get_session_id(request)},
    )
    return {"ok": True, **result}


@router.get("/api/download-log-archive")
def api_download_log_archive(
    request: Request,
    device_type: str = "ORIN",
    module_names: str = "",
    start_at: str = "",
    end_at: str = "",
    root: str = "/home/naviai/navi_project/logs",
):
    session = get_session(request)
    client, should_close_target_client, target = create_package_target_client(session, device_type)
    try:
        resolved_root, selected_modules, files = collect_log_files(
            client=client,
            root=root,
            module_names=module_names,
            start_at=start_at,
            end_at=end_at,
        )
        if not files:
            raise ApiError("当前筛选条件下没有可打包的日志文件", status_code=404)

        archive_name = build_log_archive_name(str(target.get("device_type") or device_type).upper(), start_at, end_at)
        archive_stream = io.BytesIO()
        with zipfile.ZipFile(archive_stream, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in files:
                remote_path = str(entry.get("path") or "").strip()
                relative_path = str(entry.get("relative_path") or os.path.basename(remote_path) or "log.txt").strip()
                if not remote_path or not relative_path:
                    continue
                archive.writestr(relative_path, client.read_file_bytes(remote_path))

            manifest_lines = [
                f"device_type: {str(target.get('device_type') or device_type).upper()}",
                f"resolved_root: {resolved_root}",
                f"module_names: {', '.join(sorted(selected_modules)) if selected_modules else 'ALL'}",
                f"start_at: {str(start_at or '').strip() or '-'}",
                f"end_at: {str(end_at or '').strip() or '-'}",
                f"file_count: {len(files)}",
                "",
                "files:",
            ]
            manifest_lines.extend(f"- {str(entry.get('relative_path') or entry.get('path') or '').strip()}" for entry in files)
            archive.writestr("_manifest.txt", "\n".join(manifest_lines).strip() + "\n")

        archive_stream.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="{archive_name}"'}
        return StreamingResponse(archive_stream, media_type="application/zip", headers=headers)
    finally:
        if should_close_target_client:
            client.close()


@router.get("/api/scan-paths")
def api_scan_paths(request: Request, root: str = "/", keyword: str = ""):
    result = tool_registry.call_tool(
        "remote_scan_paths",
        {"root": root, "keyword": keyword, "device_type": "ORIN"},
        {"session_id": get_session_id(request)},
    )
    return {"ok": True, **result}


@router.get("/api/tools")
def api_tools():
    return {"ok": True, "items": tool_registry.list_definitions()}


@router.post("/api/tools/call")
def api_tool_call(payload: ToolCallPayload, request: Request):
    result = tool_registry.call_tool(
        payload.name,
        payload.arguments,
        {"session_id": get_session_id(request)},
    )
    return {"ok": True, "result": result}


@router.post("/api/replace-file")
def api_replace_file(
    request: Request,
    remote_path: str = Form(...),
    backup_before_replace: str | None = Form(None),
    upload_token: str = Form(""),
    replace_file: UploadFile | None = File(None),
):
    session = get_session(request)
    session_id = get_session_id(request)
    client = ensure_client_connected(session)
    upload = require_upload(replace_file, "请上传要替换的本地文件")
    target_path = client.resolve_remote_path(require_text(remote_path, "目标远程文件不能为空"))
    raw_bytes = upload.file.read()
    try:
        upload_progress_manager.start(
            upload_token,
            file_name=os.path.basename(upload.filename or target_path),
            total_bytes=len(raw_bytes),
            phase="preparing",
            message="正在准备替换远程文件",
            owner_id=session_id,
        )
        backup_path = None
        if parse_bool(backup_before_replace):
            upload_progress_manager.update(upload_token, phase="backing_up", message="正在备份远端文件")
            backup_path = client.backup_remote_path(target_path, sudo_password=current_robot_password(session))
        client.upload_bytes(
            raw_bytes,
            target_path,
            progress_callback=lambda transferred, total: upload_progress_manager.update(
                upload_token,
                transferred_bytes=transferred,
                total_bytes=total,
                phase="uploading_to_robot",
                message=f"正在上传到机器人: {target_path}",
            ),
        )
        upload_progress_manager.update(
            upload_token,
            transferred_bytes=len(raw_bytes),
            total_bytes=len(raw_bytes),
            phase="completed",
            message=f"文件已上传并替换: {target_path}",
            done=True,
        )
        history_id = build_file_replace_history(session, target_path, backup_path, {"remote_path": target_path, "backup_path": backup_path or ""})
        return {"ok": True, "message": f"已替换远程文件 {target_path}", "backup_path": backup_path, "history_id": history_id}
    except Exception as exc:  # noqa: BLE001
        upload_progress_manager.fail(upload_token, f"替换失败: {exc}")
        raise
