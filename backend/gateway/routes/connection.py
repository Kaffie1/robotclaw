import os

from fastapi import APIRouter, Request

from ...core.config import APP_EDITION
from ...core.models import ApiError, ConnectPayload, ConnectionConfig
from ...runtime.operations.services import refresh_remote_shortcuts
from ...core.validation import require_text
from ...infra.container import connection_cache_store, deploy_config_store
from ...runtime.workflow.playbook_state import clear_live_playbook_state
from ...runtime.workflow.confirmation import delete_chat_history_file, reset_chat_state
from ..support import get_session, get_session_id, hydrate_session_last_config_from_cache

router = APIRouter()


@router.get("/api/status")
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


@router.post("/api/connect")
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
    return {
        "ok": True,
        "message": message,
        "remote_shortcuts": shortcut_payload["shortcuts"],
        "preferred_root": shortcut_payload["preferred_root"],
        "saved_connections": saved_connections,
    }


@router.post("/api/disconnect")
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


@router.get("/api/connection-cache")
def api_connection_cache():
    return {"ok": True, "saved_connections": connection_cache_store.list_entries()}


@router.post("/api/connection-cache/clear")
def api_clear_connection_cache():
    return {"ok": True, "message": "连接缓存已清空", "saved_connections": connection_cache_store.clear()}


@router.get("/api/remote-shortcuts")
def api_remote_shortcuts(request: Request):
    from ...runtime.tools import tool_registry

    result = tool_registry.call_tool(
        "remote_shortcuts",
        {"device_type": "ORIN"},
        {"session_id": get_session_id(request)},
    )
    return {"ok": True, "shortcuts": result["shortcuts"], "preferred_root": result["preferred_root"]}
