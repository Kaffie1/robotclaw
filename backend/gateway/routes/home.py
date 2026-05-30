from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ...core.config import APP_EDITION
from ...core.files import get_asset_version
from ...infra.container import connection_cache_store, deploy_config_store, templates
from ..support import build_connection_summary_label, get_session, hydrate_session_last_config_from_cache

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
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
