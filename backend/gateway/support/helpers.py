import re
from datetime import datetime
from typing import Any

from ...core.models import ApiError
from ...infra.container import connection_cache_store

_GZ_LOG_NAME_PATTERN = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d{1,6})?)\..*\.gz$",
    re.IGNORECASE,
)


def resolve_log_filter_timestamp(entry: dict[str, Any]) -> int:
    name = str(entry.get("name") or "").strip()
    if name.lower().endswith(".gz"):
        match = _GZ_LOG_NAME_PATTERN.match(name)
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
