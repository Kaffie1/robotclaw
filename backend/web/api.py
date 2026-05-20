import json
import io
import os
import posixpath
import re
import threading
import traceback
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..tools import tool_registry
from ..core.config import (
    DEPLOY_CONFIG_PATH,
    MAX_TASK_ITEMS,
    MODULE_DEPLOY_ROOT,
    SESSION_CLEANUP_INTERVAL_SECONDS,
    SESSION_COOKIE,
    SESSION_IDLE_TIMEOUT_SECONDS,
    STATIC_DIR,
)
from ..common import (
    get_asset_version,
    parse_bool,
    prepare_package_bytes,
    prepare_package_source,
    render_remote_command,
    require_text,
    require_upload,
    resolve_download_source_path,
)
from ..core.models import ApiError, ConnectPayload, ConnectionConfig, ExecutePayload, InstallDebPayload, RosServiceCallPayload, RosTopicPublishPayload, ToolCallPayload
from ..shared.runtime import connection_cache_store, deploy_config_store, history_store, session_store, task_manager, templates, upload_progress_manager
from ..tools.ros import (
    ros_list_services,
    ros_list_topics,
    ros_message_definition,
    ros_service_call,
    ros_service_definition_by_name,
    ros_service_info,
    ros_service_type,
    ros_topic_echo,
    ros_topic_info,
    ros_topic_publish,
    ros_topic_type,
)
from ..operations.workflow import (
    create_package_target_client,
    create_package_workflow_task_runner,
    create_module_workflow_task_runner,
    resolve_deploy_target,
)
from ..operations.services import (
    build_file_replace_history,
    create_history_rollback_runner,
    current_robot_password,
    ensure_client_connected,
    refresh_remote_shortcuts,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """定期清理过期会话数据的生命周期管理器"""
    stop_event = threading.Event()

    def cleanup_loop() -> None:
        while not stop_event.wait(SESSION_CLEANUP_INTERVAL_SECONDS):
            session_store.cleanup_expired(SESSION_IDLE_TIMEOUT_SECONDS)

    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        cleanup_thread.join(timeout=1)
        session_store.close_all()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例"""
    app = FastAPI(title="Robot Upgrade Console", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    gz_log_name_pattern = re.compile(
        r"^(?P<stamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d{1,6})?)\..*\.gz$",
        re.IGNORECASE,
    )

    def resolve_log_filter_timestamp(entry: dict[str, Any]) -> int:
        name = str(entry.get("name") or "").strip()
        if name.lower().endswith(".gz"):
            match = gz_log_name_pattern.match(name)
            if match:
                stamp = match.group("stamp")
                for fmt in ("%Y-%m-%d_%H-%M-%S-%f", "%Y-%m-%d_%H-%M-%S"):
                    try:
                        return int(datetime.strptime(stamp, fmt).timestamp())
                    except ValueError:
                        continue
        created_at = int(entry.get("created_at") or 0)
        if created_at <= 0:
            raise ApiError(f"日志文件缺少可用创建时间，无法筛选: {str(entry.get('path') or name).strip()}")
        return created_at

    def collect_log_files(
        *,
        client,
        root: str,
        module_names: str,
        start_at: str,
        end_at: str,
    ) -> tuple[str, set[str], list[dict[str, Any]]]:
        resolved_root = client.resolve_remote_path(root)
        files = client.list_files_recursive(resolved_root, require_birth_time=False)
        selected_modules = {
            item.strip()
            for item in str(module_names or "").split(",")
            if item.strip()
        }
        if selected_modules:
            files = [
                entry
                for entry in files
                if str(entry.get("relative_path") or "").split("/", 1)[0] in selected_modules
            ]
        start_ts = None
        end_ts = None
        if str(start_at or "").strip():
            start_ts = int(datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S").timestamp())
        if str(end_at or "").strip():
            end_ts = int(datetime.strptime(end_at, "%Y-%m-%d %H:%M:%S").timestamp())
        for entry in files:
            entry["filter_timestamp"] = resolve_log_filter_timestamp(entry)
        if start_ts is not None:
            files = [entry for entry in files if int(entry.get("filter_timestamp") or 0) >= start_ts]
        if end_ts is not None:
            files = [entry for entry in files if int(entry.get("filter_timestamp") or 0) <= end_ts]
        return resolved_root, selected_modules, files

    def build_log_archive_name(device_type: str, start_at: str, end_at: str) -> str:
        prefix = str(device_type or "log").strip().lower() or "log"
        start_label = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S").strftime("%m%d%H%M")
        end_label = datetime.strptime(end_at, "%Y-%m-%d %H:%M:%S").strftime("%m%d%H%M")
        return f"{prefix}-{start_label}-{end_label}.zip"

    @app.middleware("http")
    async def attach_session(request: Request, call_next):
        sid = request.cookies.get(SESSION_COOKIE)
        sid, session, is_new = session_store.get_or_create(sid)
        session_store.touch(sid)
        request.state.session_id = sid
        request.state.session = session
        response = await call_next(request)
        if is_new:
            response.set_cookie(SESSION_COOKIE, sid, path="/", httponly=True, samesite="lax")
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.message, **exc.payload})
        return PlainTextResponse(exc.message, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        message = errors[0].get("msg", "请求参数无效") if errors else "请求参数无效"
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=400, content={"ok": False, "error": message})
        return PlainTextResponse(message, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": str(exc.detail)})
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        traceback.print_exc()
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        return PlainTextResponse(str(exc), status_code=500)

    def get_session(request: Request) -> dict[str, Any]:
        return request.state.session

    def get_session_id(request: Request) -> str:
        return str(request.state.session_id or "")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        session = get_session(request)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "defaults": session["last_config"],
                "connected": session["client"].connected,
                "saved_connections": connection_cache_store.list_entries(),
                "package_machine_options": deploy_config_store.get_machine_options("package"),
                "module_machine_options": deploy_config_store.get_machine_options("module"),
                "asset_version": get_asset_version(),
            },
        )

    @app.get("/api/status")
    def api_status(request: Request):
        session = get_session(request)
        if session["client"].connected and not session.get("remote_shortcuts"):
            refresh_remote_shortcuts(session)
        return {
            "ok": True,
            "session_id": get_session_id(request),
            "connected": session["client"].connected,
            "last_config": session["last_config"],
            "last_remote_deb_path": session["last_remote_deb_path"],
            "remote_shortcuts": session.get("remote_shortcuts", []),
            "preferred_root": session.get("preferred_root", "/"),
            "saved_connections": connection_cache_store.list_entries(),
            "package_machine_options": deploy_config_store.get_machine_options("package"),
            "module_machine_options": deploy_config_store.get_machine_options("module"),
        }

    @app.post("/api/connect")
    def api_connect(payload: ConnectPayload, request: Request):
        session = get_session(request)
        host = require_text(payload.host, "主机不能为空")
        username = require_text(payload.username, "用户名不能为空")
        password = str(payload.password or "")
        pico_host = str(payload.pico_host or "").strip()
        pico_username = str(payload.pico_username or "").strip()
        pico_password = str(payload.pico_password or "")
        if not password:
            raise ApiError("请填写密码")
        config = ConnectionConfig(host=host, port=int(payload.port), username=username, password=password)
        session["client"].connect(config)
        session["last_config"] = {
            "host": host,
            "port": int(payload.port),
            "username": username,
            "pico_host": pico_host,
            "pico_port": int(payload.pico_port),
            "pico_username": pico_username,
        }
        session["ssh_auth"] = {"username": username, "password": password}
        session["processor_auth"] = {
            "ORIN": {"host": host, "port": int(payload.port), "username": username, "password": password},
            "PICO": {"host": pico_host, "port": int(payload.pico_port), "username": pico_username, "password": pico_password},
        }
        saved_connections = connection_cache_store.remember(
            {
                "host": host,
                "port": int(payload.port),
                "username": username,
                "password": password,
                "pico_host": pico_host,
                "pico_port": int(payload.pico_port),
                "pico_username": pico_username,
                "pico_password": pico_password,
            }
        )
        shortcut_payload = refresh_remote_shortcuts(session)
        return {"ok": True, "message": "连接成功", "remote_shortcuts": shortcut_payload["shortcuts"], "preferred_root": shortcut_payload["preferred_root"], "saved_connections": saved_connections}

    @app.post("/api/disconnect")
    def api_disconnect(request: Request):
        session = get_session(request)
        session["client"].close()
        session["remote_shortcuts"] = []
        session["preferred_root"] = "/"
        session["ssh_auth"] = {"username": str(session["last_config"].get("username") or ""), "password": ""}
        session["processor_auth"] = {
            "ORIN": {
                "host": str(session["last_config"].get("host") or ""),
                "port": int(session["last_config"].get("port") or 22),
                "username": str(session["last_config"].get("username") or ""),
                "password": "",
            },
            "PICO": {
                "host": str(session["last_config"].get("pico_host") or ""),
                "port": int(session["last_config"].get("pico_port") or 22),
                "username": str(session["last_config"].get("pico_username") or ""),
                "password": "",
            },
        }
        return {"ok": True, "message": "已断开连接"}

    @app.get("/api/connection-cache")
    def api_connection_cache():
        return {"ok": True, "saved_connections": connection_cache_store.list_entries()}

    @app.post("/api/connection-cache/clear")
    def api_clear_connection_cache():
        return {"ok": True, "message": "连接缓存已清空", "saved_connections": connection_cache_store.clear()}

    @app.get("/api/remote-shortcuts")
    def api_remote_shortcuts(request: Request):
        result = tool_registry.call_tool(
            "remote_shortcuts",
            {"device_type": "ORIN"},
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, "shortcuts": result["shortcuts"], "preferred_root": result["preferred_root"]}

    @app.get("/api/upload-progress/{upload_token}")
    def api_upload_progress(upload_token: str, request: Request):
        return {"ok": True, "progress": upload_progress_manager.get(upload_token, get_session_id(request))}

    @app.get("/api/ping")
    def api_ping(request: Request):
        session = get_session(request)
        return {
            "ok": True,
            "session_id": get_session_id(request),
            "connected": bool(session["client"].connected),
        }

    @app.get("/api/ros/topics")
    def api_ros_topics(request: Request):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_list_topics(client)}

    @app.get("/api/ros/services")
    def api_ros_services(request: Request):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_list_services(client)}

    @app.get("/api/ros/topic-info")
    def api_ros_topic_info(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_topic_info(client, name)}

    @app.get("/api/ros/topic-type")
    def api_ros_topic_type(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_topic_type(client, name)}

    @app.get("/api/ros/message-definition")
    def api_ros_message_definition(request: Request, type_name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_message_definition(client, type_name)}

    @app.get("/api/ros/topic-echo")
    def api_ros_topic_echo(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_topic_echo(client, name, timeout=15.0, line_limit=120)}

    @app.post("/api/ros/topic-pub")
    def api_ros_topic_pub(payload: RosTopicPublishPayload, request: Request):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_topic_publish(client, payload.name, payload.message_type, payload.message)}

    @app.get("/api/ros/service-info")
    def api_ros_service_info(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_service_info(client, name)}

    @app.get("/api/ros/service-type")
    def api_ros_service_type(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_service_type(client, name)}

    @app.get("/api/ros/service-definition")
    def api_ros_service_definition(request: Request, name: str = ""):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_service_definition_by_name(client, name)}

    @app.post("/api/ros/service-call")
    def api_ros_service_call(payload: RosServiceCallPayload, request: Request):
        client = ensure_client_connected(get_session(request))
        return {"ok": True, **ros_service_call(client, payload.name, payload.request)}

    @app.get("/api/deploy-target")
    def api_deploy_target(request: Request, file_name: str = "", machine_type: str = "", device_type: str = "ORIN"):
        session = get_session(request)
        client, should_close_target_client, _ = create_package_target_client(
            session,
            device_type,
        )
        try:
            resolved_remote_dir, normalized_file_name, remote_path = resolve_deploy_target(client, file_name)
            return {"ok": True, "remote_dir": resolved_remote_dir, "file_name": normalized_file_name, "remote_path": remote_path, "exists": client.path_exists(remote_path)}
        finally:
            if should_close_target_client:
                client.close()

    @app.post("/api/deploy")
    def api_deploy(request: Request, machine_type: str = Form(""), device_type: str = Form("ORIN"), server_file_path: str = Form(""), auto_deploy: str = Form(""), upload_token: str = Form(""), deb_file: UploadFile | None = File(None)):
        """部署接口，支持上传安装包文件或指定服务器文件路径，并根据部署配置自动选择部署方案"""
        """request: 请求对象
            machine_type: 机器类型，用于选择部署配置
            device_type: 设备类型，用于选择部署目标
            server_file_path: 服务器文件路径，用于从文件服务器下载安装包
            auto_deploy: 是否自动部署，如果为true且部署配置中auto_rollback为true，则部署失败时会自动执行回滚，true/false，默认为false
            upload_token: 上传进度标识，用于文件上传和服务器下载进度的关联
            deb_file: 上传的安装包文件，可选，如果提供则优先使用该文件进行部署，否则使用server_file_path指定的服务器文件路径"""
        session = get_session(request)
        session_id = get_session_id(request)
        client, should_close_target_client, target = create_package_target_client(
            session,
            device_type,
        )
        try:
            selected_file_name, source_metadata = prepare_package_source(
                deb_file,
                server_file_path,
                local_error_message="请选择要部署的安装包文件或填写文件服务器包路径",
            )
            resolved_remote_dir, selected_file_name, remote_path = resolve_deploy_target(client, selected_file_name)
            deploy_profile = deploy_config_store.get_profile("package", machine_type, auto_select_default=bool(str(machine_type or "").strip()))
            title, metadata, runner = create_package_workflow_task_runner(
                session,
                remote_dir=resolved_remote_dir,
                machine_type=str(deploy_profile.get("machine_type") or ""),
                device_type=str(target.get("device_type") or device_type).upper(),
                rollback_template=deploy_profile["rollback_template"],
                file_name=selected_file_name,
                source_metadata=source_metadata,
                cleanup_existing_remote_files=True,
                upload_token=str(upload_token or "").strip(),
                owner_id=session_id,
            )
            metadata.update(
                {
                    "deploy_mode": "package", 
                    "remote_dir": resolved_remote_dir, 
                    "remote_path": remote_path, 
                    "deploy_config_path": str(DEPLOY_CONFIG_PATH), 
                    "machine_type": str(deploy_profile.get("machine_type") or ""), 
                    "device_type": str(target.get("device_type") or device_type).upper(), 
                    "target_host": str(target.get("host") or ""), 
                    "target_port": int(target.get("port") or 22), 
                    "target_username": str(target.get("username") or ""), 
                    "source_kind": str(source_metadata.get("source_kind") or ""), 
                    "source_path": str(source_metadata.get("source_path") or ""), 
                    "download_path": str(source_metadata.get("download_path") or "")
                }
            )
            return {"ok": True, "task": task_manager.create_task("deployment", title, metadata, runner, owner_id=session_id)}
        finally:
            if should_close_target_client:
                client.close()

    @app.post("/api/deploy-module")
    def api_deploy_module(
        request: Request,
        module_name: str = Form(""),
        server_file_path: str = Form(""),
        server_file_paths_json: str = Form(""),
        auto_module_version: str = Form(""),
        auto_deploy: str = Form(""),
        upload_token: str = Form(""),
        deb_file: UploadFile | None = File(None),
    ):
        session = get_session(request)
        session_id = get_session_id(request)
        client = ensure_client_connected(session)
        auto_deploy_flag = parse_bool(auto_deploy)
        selected_module_name = require_text(module_name, "请选择要部署的模块")
        selected_module_path = client.resolve_remote_path(posixpath.join(MODULE_DEPLOY_ROOT, selected_module_name))
        if not client.path_exists(selected_module_path):
            raise ApiError(f"模块目录不存在: {selected_module_path}")
        if not client.is_dir_path(selected_module_path):
            raise ApiError(f"模块路径不是目录: {selected_module_path}")
        package_sources: list[dict[str, Any]] = []
        batch_server_paths: list[str] = []
        if str(server_file_paths_json or "").strip():
            try:
                raw_paths = json.loads(server_file_paths_json)
            except json.JSONDecodeError as exc:
                raise ApiError(f"自动部署包路径配置解析失败: {exc}") from exc
            if not isinstance(raw_paths, list):
                raise ApiError("自动部署包路径格式错误，应为数组")
            batch_server_paths = [str(item or "").strip() for item in raw_paths if str(item or "").strip()]
        if batch_server_paths:
            for path in batch_server_paths:
                package_file_name, source_metadata = prepare_package_source(
                    None,
                    path,
                    local_error_message="请选择要部署的模块 deb 文件或填写文件服务器包路径",
                )
                package_sources.append(
                    {
                        "package_file_name": package_file_name,
                        "source_metadata": source_metadata,
                    }
                )
        else:
            package_file_name, source_metadata = prepare_package_source(
                deb_file,
                server_file_path,
                local_error_message="请选择要部署的模块 deb 文件或填写文件服务器包路径",
            )
            package_sources.append(
                {
                    "package_file_name": package_file_name,
                    "source_metadata": source_metadata,
                }
            )
        deploy_profile = deploy_config_store.get_profile("module", selected_module_name)
        title, metadata, runner = create_module_workflow_task_runner(
            session,
            module_name=selected_module_name,
            module_path=selected_module_path,
            package_sources=package_sources,
            auto_deploy_version=str(auto_module_version or "").strip(),
            upload_token=str(upload_token or "").strip(),
            up_wait_seconds=int(deploy_profile.get("up_wait_seconds") or 0),
            auto_deploy=auto_deploy_flag,
            owner_id=session_id,
        )
        first_package_name = str(package_sources[0].get("package_file_name") or "")
        first_source_metadata = package_sources[0].get("source_metadata") if isinstance(package_sources[0].get("source_metadata"), dict) else {}
        metadata.update(
            {
                "deploy_mode": "module",
                "module_name": selected_module_name,
                "module_path": selected_module_path,
                "up_wait_seconds": int(deploy_profile.get("up_wait_seconds") or 0),
                "package_file_name": first_package_name,
                "package_file_names": [str(item.get("package_file_name") or "") for item in package_sources],
                "package_count": len(package_sources),
                "auto_deploy": auto_deploy_flag,
                "auto_deploy_version": str(auto_module_version or "").strip(),
                "package_prefix": first_package_name.split("_", 1)[0].strip() if first_package_name else "",
                "remote_path": client.resolve_remote_path(posixpath.join(selected_module_path, first_package_name)) if first_package_name else selected_module_path,
                "remote_paths": [
                    client.resolve_remote_path(posixpath.join(selected_module_path, str(item.get("package_file_name") or "")))
                    for item in package_sources
                    if str(item.get("package_file_name") or "").strip()
                ],
                "deploy_config_path": str(DEPLOY_CONFIG_PATH),
                "source_kind": str(first_source_metadata.get("source_kind") or ""),
                "source_path": str(first_source_metadata.get("source_path") or ""),
                "download_path": str(first_source_metadata.get("download_path") or ""),
            }
        )
        return {"ok": True, "task": task_manager.create_task("deployment", title, metadata, runner, owner_id=session_id)}

    @app.get("/api/tasks")
    def api_tasks(request: Request, limit: int = MAX_TASK_ITEMS):
        owner_id = get_session_id(request)
        tasks = task_manager.list_tasks_for_owner(owner_id, limit=limit)
        return {"ok": True, "tasks": tasks}

    @app.get("/api/tasks/{task_id}")
    def api_task_detail(task_id: str, request: Request):
        owner_id = get_session_id(request)
        task = task_manager.get_task_for_owner(task_id, owner_id)
        if not task:
            raise ApiError("任务不存在", status_code=404)
        return {"ok": True, "task": task}

    @app.post("/api/tasks/{task_id}/continue")
    async def api_task_continue(task_id: str, request: Request):
        owner_id = get_session_id(request)
        body = await request.json()
        message = str(body.get("message") or "").strip()
        if not message:
            raise ApiError("确认输入不能为空", status_code=400)
        task = task_manager.continue_task(task_id, message, owner_id=owner_id)
        if not task:
            raise ApiError("任务不存在或当前不处于等待确认状态", status_code=404)
        return {"ok": True, "task": task}

    @app.get("/api/history")
    def api_history(request: Request, limit: int = 20):
        return {"ok": True, "history": history_store.list_entries(limit=limit, owner_id=get_session_id(request))}

    @app.post("/api/history/{entry_id}/rollback")
    def api_history_rollback(entry_id: int, request: Request):
        entry = history_store.get_entry(entry_id, owner_id=get_session_id(request))
        if not entry:
            raise ApiError("历史记录不存在", status_code=404)
        title, runner = create_history_rollback_runner(get_session(request), entry)
        return {"ok": True, "task": task_manager.create_task("rollback", title, {"source_history_id": entry_id, "operation_type": entry["operation_type"]}, runner, owner_id=get_session_id(request))}

    @app.post("/api/upload-deb")
    def api_upload_deb(request: Request, remote_dir: str = Form(...), command_template: str = Form("dpkg -i {deb_path}"), install_after_upload: str | None = Form(None), upload_token: str = Form(""), deb_file: UploadFile | None = File(None)):
        session = get_session(request)
        session_id = get_session_id(request)
        client = ensure_client_connected(session)
        upload = require_upload(deb_file, "请上传 deb 文件")
        remote_dir = require_text(remote_dir, "远程目录不能为空")
        filename = os.path.basename(upload.filename or "package.deb")
        raw_bytes = upload.file.read()
        try:
            upload_progress_manager.start(upload_token, file_name=filename, total_bytes=len(raw_bytes), phase="uploading_to_robot", message="正在上传到机器人", owner_id=session_id)
            remote_path = client.resolve_remote_path(posixpath.join(remote_dir, filename))
            client.upload_bytes(raw_bytes, remote_path, progress_callback=lambda transferred, total: upload_progress_manager.update(upload_token, transferred_bytes=transferred, total_bytes=total, phase="uploading_to_robot", message=f"正在上传到机器人: {remote_path}"))
            session["last_remote_deb_path"] = remote_path
            install_result = None
            install_command = None
            if parse_bool(install_after_upload):
                upload_progress_manager.update(upload_token, transferred_bytes=len(raw_bytes), total_bytes=len(raw_bytes), phase="installing", message="安装包上传完成，正在执行安装命令")
                install_command = render_remote_command(str(command_template or "dpkg -i {deb_path}"), remote_path)
                install_result = client.exec_noninteractive_command(install_command)
            upload_progress_manager.update(upload_token, transferred_bytes=len(raw_bytes), total_bytes=len(raw_bytes), phase="completed", message=f"安装包处理完成: {remote_path}", done=True)
            return {"ok": True, "message": f"deb 已上传到 {remote_path}", "remote_path": remote_path, "install_command": install_command, "install_result": install_result}
        except Exception as exc:  # noqa: BLE001
            upload_progress_manager.fail(upload_token, f"上传失败: {exc}")
            raise

    @app.post("/api/install-deb")
    def api_install_deb(payload: InstallDebPayload, request: Request):
        session = get_session(request)
        remote_path = require_text(payload.remote_path, "远程 deb 路径不能为空")
        command = render_remote_command(str(payload.command_template or "dpkg -i {deb_path}"), remote_path)
        result = ensure_client_connected(session).exec_noninteractive_command(command)
        session["last_remote_deb_path"] = remote_path
        return {"ok": True, "command": command, "result": result}

    @app.post("/api/execute")
    def api_execute(payload: ExecutePayload, request: Request):
        result = tool_registry.call_tool(
            "remote_execute_readonly",
            payload.model_dump(),
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, "result": result["result"], "command": result["command"], "interactive": result["interactive"], "device_type": result["device_type"]}

    @app.get("/api/list-dir")
    def api_list_dir(request: Request, path: str = "/", device_type: str = "ORIN"):
        result = tool_registry.call_tool(
            "remote_list_dir",
            {"path": path, "device_type": device_type},
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, **result}

    @app.get("/api/download-log-archive")
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

    @app.get("/api/scan-paths")
    def api_scan_paths(request: Request, root: str = "/", keyword: str = ""):
        result = tool_registry.call_tool(
            "remote_scan_paths",
            {"root": root, "keyword": keyword, "device_type": "ORIN"},
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, **result}

    @app.get("/api/tools")
    def api_tools():
        return {"ok": True, "items": tool_registry.list_definitions()}

    @app.post("/api/tools/call")
    def api_tool_call(payload: ToolCallPayload, request: Request):
        result = tool_registry.call_tool(
            payload.name,
            payload.arguments,
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, "result": result}

    @app.post("/api/replace-file")
    def api_replace_file(request: Request, remote_path: str = Form(...), backup_before_replace: str | None = Form(None), upload_token: str = Form(""), replace_file: UploadFile | None = File(None)):
        session = get_session(request)
        session_id = get_session_id(request)
        client = ensure_client_connected(session)
        upload = require_upload(replace_file, "请上传要替换的本地文件")
        target_path = client.resolve_remote_path(require_text(remote_path, "目标远程文件不能为空"))
        raw_bytes = upload.file.read()
        try:
            upload_progress_manager.start(upload_token, file_name=os.path.basename(upload.filename or target_path), total_bytes=len(raw_bytes), phase="preparing", message="正在准备替换远程文件", owner_id=session_id)
            backup_path = None
            if parse_bool(backup_before_replace):
                upload_progress_manager.update(upload_token, phase="backing_up", message="正在备份远端文件")
                backup_path = client.backup_remote_path(target_path, sudo_password=current_robot_password(session))
            client.upload_bytes(raw_bytes, target_path, progress_callback=lambda transferred, total: upload_progress_manager.update(upload_token, transferred_bytes=transferred, total_bytes=total, phase="uploading_to_robot", message=f"正在上传到机器人: {target_path}"))
            upload_progress_manager.update(upload_token, transferred_bytes=len(raw_bytes), total_bytes=len(raw_bytes), phase="completed", message=f"文件已上传并替换: {target_path}", done=True)
            history_id = build_file_replace_history(session, target_path, backup_path, {"remote_path": target_path, "backup_path": backup_path or ""})
            return {"ok": True, "message": f"已替换远程文件 {target_path}", "backup_path": backup_path, "history_id": history_id}
        except Exception as exc:  # noqa: BLE001
            upload_progress_manager.fail(upload_token, f"替换失败: {exc}")
            raise

    return app
