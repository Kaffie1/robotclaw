import asyncio
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
from ..agent import run_fault_chat_graph
from ..agent.playbook_state import (
    build_matched_playbook_payload_by_id,
    clear_live_playbook_state,
    get_live_playbook_state,
    reset_live_playbook_execution,
    stream_live_playbook_events,
)
from ..agent.graph_nodes import load_catalog_node, resolve_playbook_route
from ..core.config import (
    APP_EDITION,
    DEPLOY_CONFIG_PATH,
    MAX_TASK_ITEMS,
    MODULE_DEPLOY_ROOT,
    SESSION_CLEANUP_INTERVAL_SECONDS,
    SESSION_COOKIE,
    SESSION_IDLE_TIMEOUT_SECONDS,
    STATIC_DIR,
)
from ..shared import (
    append_chat_history_turn,
    delete_chat_history_file,
    get_asset_version,
    get_chat_history,
    logger,
    parse_bool,
    prepare_package_bytes,
    prepare_package_source,
    require_text,
    require_upload,
    reset_chat_state,
    resolve_download_source_path,
)
from ..core.models import ApiError, ConnectPayload, ConnectionConfig, ExecutePayload, ToolCallPayload
from ..shared.runtime import connection_cache_store, deploy_config_store, history_store, session_store, task_manager, templates, upload_progress_manager
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

    def hydrate_session_last_config_from_cache(session: dict[str, Any]) -> None:
        if not isinstance(session, dict):
            return
        last_config = session.get("last_config") if isinstance(session.get("last_config"), dict) else {}
        host = str(last_config.get("host") or "").strip()
        username = str(last_config.get("username") or "").strip()
        if host and username:
            return
        saved_connections = connection_cache_store.list_entries()
        if not saved_connections:
            return
        latest = saved_connections[0] if isinstance(saved_connections[0], dict) else {}
        latest_host = str(latest.get("host") or "").strip()
        latest_username = str(latest.get("username") or "").strip()
        if not latest_host or not latest_username:
            return
        session["last_config"] = {
            "host": latest_host,
            "port": int(latest.get("port") or 22),
            "username": latest_username,
            "pico_host": str(latest.get("pico_host") or "").strip(),
            "pico_port": int(latest.get("pico_port") or 22),
            "pico_username": str(latest.get("pico_username") or "").strip(),
        }
        session["ssh_auth"] = {
            "username": latest_username,
            "password": str(latest.get("password") or ""),
        }
        session["processor_auth"] = {
            "ORIN": {
                "host": latest_host,
                "port": int(latest.get("port") or 22),
                "username": latest_username,
                "password": str(latest.get("password") or ""),
            },
            "PICO": {
                "host": str(latest.get("pico_host") or "").strip(),
                "port": int(latest.get("pico_port") or 22),
                "username": str(latest.get("pico_username") or "").strip(),
                "password": str(latest.get("pico_password") or ""),
            },
        }

    def build_connection_summary_label(connection: dict[str, Any] | None) -> str:
        if not isinstance(connection, dict):
            return "暂无缓存连接"
        host = str(connection.get("host") or "").strip()
        port = int(connection.get("port") or 22)
        username = str(connection.get("username") or "").strip()
        if not host or not username:
            return "暂无缓存连接"
        summary = f"最近使用 · ORIN {host}:{port} · {username}"
        pico_host = str(connection.get("pico_host") or "").strip()
        if pico_host:
            pico_port = int(connection.get("pico_port") or 22)
            pico_username = str(connection.get("pico_username") or "").strip() or "-"
            summary += f" · PICO {pico_host}:{pico_port} · {pico_username}"
        return summary

    def summarize_playbook_execution(execution: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(execution, dict):
            return {}
        node_statuses = execution.get("node_statuses") if isinstance(execution.get("node_statuses"), dict) else {}
        compact_statuses: dict[str, str] = {}
        for path, payload in node_statuses.items():
            if isinstance(payload, dict):
                status = str(payload.get("status") or "").strip()
            else:
                status = str(payload or "").strip()
            if status:
                compact_statuses[str(path)] = status
        return {
            "overall_status": str(execution.get("overall_status") or "").strip(),
            "active_node_path": str(execution.get("active_node_path") or "").strip(),
            "node_count": len(node_statuses),
            "node_statuses": compact_statuses,
        }

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        session = get_session(request)
        hydrate_session_last_config_from_cache(session)
        saved_connections = connection_cache_store.list_entries()
        selected_connection_id = ""
        selected_connection: dict[str, Any] | None = None
        if saved_connections:
            current_config = session.get("last_config") if isinstance(session.get("last_config"), dict) else {}
            current_host = str(current_config.get("host") or "").strip()
            current_port = int(current_config.get("port") or 22)
            current_username = str(current_config.get("username") or "").strip()
            current_pico_host = str(current_config.get("pico_host") or "").strip()
            current_pico_port = int(current_config.get("pico_port") or 22)
            current_pico_username = str(current_config.get("pico_username") or "").strip()
            for connection in saved_connections:
                if not isinstance(connection, dict):
                    continue
                if (
                    str(connection.get("host") or "").strip() == current_host
                    and int(connection.get("port") or 22) == current_port
                    and str(connection.get("username") or "").strip() == current_username
                    and str(connection.get("pico_host") or "").strip() == current_pico_host
                    and int(connection.get("pico_port") or 22) == current_pico_port
                    and str(connection.get("pico_username") or "").strip() == current_pico_username
                ):
                    selected_connection_id = str(connection.get("id") or "").strip()
                    selected_connection = connection
                    break
            if not selected_connection_id:
                selected_connection = saved_connections[0] if isinstance(saved_connections[0], dict) else None
                selected_connection_id = str((selected_connection or {}).get("id") or "").strip()
        ssh_auth = session.get("ssh_auth") if isinstance(session.get("ssh_auth"), dict) else {}
        processor_auth = session.get("processor_auth") if isinstance(session.get("processor_auth"), dict) else {}
        orin_auth = processor_auth.get("ORIN") if isinstance(processor_auth.get("ORIN"), dict) else {}
        pico_auth = processor_auth.get("PICO") if isinstance(processor_auth.get("PICO"), dict) else {}
        form_defaults = {
            **dict(session.get("last_config") or {}),
            "password": str(ssh_auth.get("password") or orin_auth.get("password") or ""),
            "pico_password": str(pico_auth.get("password") or ""),
        }
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "defaults": form_defaults,
                "connected": session["client"].connected,
                "saved_connections": saved_connections,
                "selected_connection_id": selected_connection_id,
                "selected_connection_summary": build_connection_summary_label(selected_connection),
                "package_machine_options": deploy_config_store.get_machine_options("package"),
                "module_machine_options": deploy_config_store.get_machine_options("module"),
                "asset_version": get_asset_version(),
                "app_edition": APP_EDITION,
            },
        )

    @app.get("/api/status")
    def api_status(request: Request):
        session = get_session(request)
        hydrate_session_last_config_from_cache(session)
        if session["client"].connected and not session.get("remote_shortcuts"):
            refresh_remote_shortcuts(session)
        return {
            "ok": True,
            "session_id": get_session_id(request),
            "app_edition": APP_EDITION,
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
        if APP_EDITION == "robot":
            host = str(payload.host or "").strip() or "local"
            username = str(payload.username or "").strip() or os.getenv("USER") or "robot"
        else:
            host = require_text(payload.host, "主机不能为空")
            username = require_text(payload.username, "用户名不能为空")
        password = str(payload.password or "")
        pico_host = str(payload.pico_host or "").strip()
        pico_username = str(payload.pico_username or "").strip()
        pico_password = str(payload.pico_password or "")
        if APP_EDITION != "robot" and not password:
            raise ApiError("请填写密码")
        config = ConnectionConfig(host=host, port=int(payload.port), username=username, password=password)
        if APP_EDITION != "robot":
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
        message = "连接成功" if APP_EDITION != "robot" else "本机模式配置已保存"
        return {"ok": True, "message": message, "remote_shortcuts": shortcut_payload["shortcuts"], "preferred_root": shortcut_payload["preferred_root"], "saved_connections": saved_connections}

    @app.post("/api/disconnect")
    def api_disconnect(request: Request):
        session = get_session(request)
        session["client"].close()
        session["remote_shortcuts"] = []
        session["preferred_root"] = "/"
        tool_context = {"session_id": get_session_id(request)}
        reset_chat_state(tool_context)
        delete_chat_history_file(tool_context)
        clear_live_playbook_state(session_id=get_session_id(request))
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

    @app.post("/api/chat")
    async def api_chat(request: Request):
        session = get_session(request)
        session_id = get_session_id(request)
        body = await request.json()
        message = str(body.get("message") or "").strip()
        continuation = body.get("continuation")
        history = body.get("history")
        route_selection = body.get("route_selection")
        if continuation is not None and not isinstance(continuation, dict):
            return JSONResponse(content={"ok": False, "error": "continuation 必须是对象"}, status_code=400)
        if history is not None and not isinstance(history, list):
            return JSONResponse(content={"ok": False, "error": "history 必须是数组"}, status_code=400)
        if route_selection is not None and not isinstance(route_selection, dict):
            return JSONResponse(content={"ok": False, "error": "route_selection 必须是对象"}, status_code=400)
        if continuation is None and not message:
            return JSONResponse(content={"ok": False, "error": "消息内容不能为空"}, status_code=400)
        if isinstance(continuation, dict):
            user_message = str(continuation.get("user_message") or "").strip()
            if not user_message:
                return JSONResponse(content={"ok": False, "error": "continuation 缺少 user_message"}, status_code=400)
            tool_context: dict[str, Any] = {"session_id": session_id, **dict(continuation.get("tool_context") or {})}
        else:
            user_message = message
            tool_context = {"session_id": session_id}
        last_config = session.get("last_config") or {}
        route_selection_payload = build_matched_playbook_payload_by_id(str((route_selection or {}).get("playbook_id") or "").strip())
        continuation_kind = str((continuation or {}).get("kind") or "").strip() if isinstance(continuation, dict) else ""
        if isinstance(continuation, dict):
            raw_resume_state = continuation.get("resume_state")
            resume_completed_nodes = raw_resume_state.get("completed_nodes") if isinstance(raw_resume_state, dict) else {}
            logger.info(
                "API /api/chat 收到 continuation | session_id=%s | kind=%s | has_resume_state=%s | resume_completed_nodes=%s",
                session_id,
                continuation_kind,
                isinstance(raw_resume_state, dict),
                sorted(str(key) for key in (resume_completed_nodes or {}).keys()) if isinstance(resume_completed_nodes, dict) else [],
            )
        if not isinstance(continuation, dict):
            if route_selection_payload:
                reset_live_playbook_execution(session_id=session_id, playbook=route_selection_payload)
            else:
                clear_live_playbook_state(session_id=session_id)
        result = await asyncio.to_thread(
            run_fault_chat_graph,
            user_message,
            runtime_context={
                "connected": bool(session["client"].connected),
                "host": str(last_config.get("host") or ""),
                "port": str(last_config.get("port") or ""),
                "username": str(last_config.get("username") or ""),
                "preferred_root": str(session.get("preferred_root") or "/"),
                "recent_tasks": task_manager.list_tasks_for_owner(session_id, MAX_TASK_ITEMS),
            },
            tool_context=tool_context,
            conversation_history=[
                {
                    "role": str(item.get("role") or "").strip(),
                    "content": str(item.get("content") or "").strip(),
                }
                for item in (history or [])
                if isinstance(item, dict)
            ],
            resume_continuation=continuation if isinstance(continuation, dict) else None,
            confirmation_response=message if continuation_kind == "playbook_confirmation" else "",
            prefetched_playbook_id=str((route_selection or {}).get("playbook_id") or "").strip(),
            prefetched_playbook_title=str((route_selection or {}).get("playbook_title") or "").strip(),
            prefetched_reason=str((route_selection or {}).get("reason") or "").strip(),
        )
        append_chat_history_turn(
            tool_context,
            user_message=user_message,
            assistant_message=str(result.get("message") or ""),
        )
        logger.info(
            "API /api/chat 返回流程图状态 | session_id=%s | summary=%s",
            session_id,
            json.dumps(summarize_playbook_execution(result.get("playbook_execution")), ensure_ascii=False),
        )
        return {"ok": True, **result}

    @app.post("/api/chat/reset")
    def api_chat_reset(request: Request):
        session_id = get_session_id(request)
        reset_chat_state({"session_id": session_id})
        clear_live_playbook_state(session_id=session_id)
        return {"ok": True, "message": "聊天上下文已清空"}

    @app.get("/api/chat/history")
    def api_chat_history(request: Request):
        return {"ok": True, "history": get_chat_history({"session_id": get_session_id(request)})}

    @app.post("/api/chat/route")
    async def api_chat_route(request: Request):
        session_id = get_session_id(request)
        body = await request.json()
        message = str(body.get("message") or "").strip()
        continuation = body.get("continuation")
        if continuation is not None and not isinstance(continuation, dict):
            return JSONResponse(content={"ok": False, "error": "continuation 必须是对象"}, status_code=400)
        if not continuation and not message:
            return JSONResponse(content={"ok": False, "error": "消息内容不能为空"}, status_code=400)
        route_state = {
            **load_catalog_node({}),
            "session_id": session_id,
            "user_message": message,
            "resume_continuation": continuation if isinstance(continuation, dict) else None,
        }
        route_result = await asyncio.to_thread(resolve_playbook_route, route_state, publish=True)
        playbook_id = str(route_result.get("selected_playbook_id") or "").strip()
        playbook_title = str(route_result.get("selected_playbook_title") or "").strip()
        reason = str(route_result.get("reason") or "").strip()
        playbook_payload = build_matched_playbook_payload_by_id(playbook_id)
        return {
            "ok": True,
            "route_selection": {
                "playbook_id": playbook_id,
                "playbook_title": playbook_title,
                "reason": reason,
            },
            "playbook": playbook_payload,
        }

    @app.get("/api/chat/state")
    async def api_chat_state(request: Request):
        session_id = get_session_id(request)
        raw_since_version = request.query_params.get("since_version", "0")
        try:
            since_version = max(int(raw_since_version), 0)
        except ValueError:
            since_version = 0
        payload = get_live_playbook_state(session_id=session_id, since_version=since_version)
        logger.info(
            "API /api/chat/state 返回流程图状态 | session_id=%s | since_version=%s | summary=%s",
            session_id,
            since_version,
            json.dumps(summarize_playbook_execution(payload.get("playbook_execution")), ensure_ascii=False),
        )
        return {"ok": True, **payload}

    @app.get("/api/chat/events")
    async def api_chat_events(request: Request):
        session_id = get_session_id(request)
        raw_since_version = request.query_params.get("since_version", "0")
        try:
            since_version = max(int(raw_since_version), 0)
        except ValueError:
            since_version = 0
        logger.info(
            "API /api/chat/events 建立SSE | session_id=%s | since_version=%s",
            session_id,
            since_version,
        )
        return StreamingResponse(
            stream_live_playbook_events(session_id=session_id, since_version=since_version),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/agent/tools")
    def api_agent_tools():
        return {"ok": True, "items": tool_registry.list_definitions()}

    @app.post("/api/agent/tool-call")
    def api_agent_tool_call(payload: ToolCallPayload, request: Request):
        result = tool_registry.call_tool(
            payload.name,
            payload.arguments,
            {"session_id": get_session_id(request)},
        )
        return {"ok": True, "result": result}

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
    def api_deploy(request: Request, machine_type: str = Form(""), device_type: str = Form("ORIN"), server_file_path: str = Form(""), upload_token: str = Form(""), deb_file: UploadFile | None = File(None)):
        """部署接口，支持上传安装包文件或指定服务器文件路径"""
        """request: 请求对象
            machine_type: 机器类型，用于选择部署配置
            device_type: 设备类型，用于选择部署目标
            server_file_path: 服务器文件路径，用于从文件服务器下载安装包
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
        upload_token: str = Form(""),
        deb_file: UploadFile | None = File(None),
    ):
        session = get_session(request)
        session_id = get_session_id(request)
        client = ensure_client_connected(session)
        selected_module_name = require_text(module_name, "请选择要部署的模块")
        selected_module_path = client.resolve_remote_path(posixpath.join(MODULE_DEPLOY_ROOT, selected_module_name))
        if not client.path_exists(selected_module_path):
            raise ApiError(f"模块目录不存在: {selected_module_path}")
        if not client.is_dir_path(selected_module_path):
            raise ApiError(f"模块路径不是目录: {selected_module_path}")
        package_file_name, source_metadata = prepare_package_source(
            deb_file,
            server_file_path,
            local_error_message="请选择要部署的模块 deb 文件或填写文件服务器包路径",
        )
        package_sources = [
            {
                "package_file_name": package_file_name,
                "source_metadata": source_metadata,
            }
        ]
        title, metadata, runner = create_module_workflow_task_runner(
            session,
            module_name=selected_module_name,
            module_path=selected_module_path,
            package_sources=package_sources,
            upload_token=str(upload_token or "").strip(),
            owner_id=session_id,
        )
        first_package_name = str(package_sources[0].get("package_file_name") or "")
        first_source_metadata = package_sources[0].get("source_metadata") if isinstance(package_sources[0].get("source_metadata"), dict) else {}
        metadata.update(
            {
                "deploy_mode": "module",
                "module_name": selected_module_name,
                "module_path": selected_module_path,
                "package_file_name": first_package_name,
                "package_file_names": [str(item.get("package_file_name") or "") for item in package_sources],
                "package_count": len(package_sources),
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
