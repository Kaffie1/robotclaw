import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import IS_ROBOT_EDITION, MAX_CONNECTION_CACHE_ITEMS
from ..infra.robot.base import RobotClient


def create_runtime_client():
    from ..infra.robot.factory import create_runtime_client as _create_runtime_client

    return _create_runtime_client()


def normalize_connection_cache_entry(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    host = str(entry.get("host") or "").strip()
    username = str(entry.get("username") or "").strip()
    port_text = str(entry.get("port") or "").strip() or "22"
    password = str(entry.get("password") or "")
    pico_host = str(entry.get("pico_host") or "").strip()
    pico_username = str(entry.get("pico_username") or "").strip()
    pico_password = str(entry.get("pico_password") or "")
    if (not host or not username) and not IS_ROBOT_EDITION:
        return None
    if not host:
        host = "local"
    if not username:
        username = "robot"
    try:
        port = int(port_text)
    except ValueError:
        port = 22
    try:
        pico_port = int(entry.get("pico_port") or 22)
    except ValueError:
        pico_port = 22
    saved_at = str(entry.get("saved_at") or "")
    return {
        "id": f"{host}|{port}|{username}",
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "pico_host": pico_host,
        "pico_port": pico_port,
        "pico_username": pico_username,
        "pico_password": pico_password,
        "saved_at": saved_at,
    }


class ConnectionCacheStore:
    def __init__(self, cache_path: Path, max_items: int = MAX_CONNECTION_CACHE_ITEMS) -> None:
        self.cache_path = cache_path
        self.max_items = max_items
        self.lock = threading.Lock()

    def list_entries(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._read_entries()

    def remember(self, connection: dict[str, Any]) -> list[dict[str, Any]]:
        normalized = normalize_connection_cache_entry({**connection, "saved_at": datetime.now().isoformat(timespec="seconds")})
        if normalized is None:
            return self.list_entries()
        with self.lock:
            entries = [normalized, *[item for item in self._read_entries() if item["id"] != normalized["id"]]]
            entries = entries[: self.max_items]
            self._write_entries(entries)
            return entries

    def clear(self) -> list[dict[str, Any]]:
        with self.lock:
            self._write_entries([])
            return []

    def _read_entries(self) -> list[dict[str, Any]]:
        if not self.cache_path.exists():
            return []
        try:
            raw = self.cache_path.read_text(encoding="utf-8")
            parsed = json.loads(raw or "[]")
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(parsed, list):
            return []
        items = [normalize_connection_cache_entry(entry) for entry in parsed]
        return [item for item in items if item]

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.cache_path.with_suffix(f"{self.cache_path.suffix}.tmp")
        temp_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.cache_path)


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def _release_session_resources(self, session: dict[str, Any]) -> None:
        client = session.get("client")
        if isinstance(client, RobotClient):
            client.close()
        session["chat_state"] = {}

    def get_or_create(self, sid: str | None) -> tuple[str, dict[str, Any], bool]:
        with self.lock:
            if sid and sid in self.sessions:
                self.sessions[sid]["last_seen_ts"] = time.time()
                return sid, self.sessions[sid], False
            new_sid = secrets.token_hex(16)
            self.sessions[new_sid] = {
                "session_id": new_sid,
                "client": create_runtime_client(),
                "last_seen_ts": time.time(),
                "path_cache": [],
                "last_remote_deb_path": "",
                "remote_shortcuts": [],
                "preferred_root": "/",
                "chat_state": {},
                "last_config": {
                    "host": "",
                    "port": 22,
                    "username": "",
                    "pico_host": "192.168.217.66",
                    "pico_port": 22,
                    "pico_username": "nav01",
                },
                "ssh_auth": {"username": "", "password": ""},
                "processor_auth": {
                    "ORIN": {"host": "", "port": 22, "username": "", "password": ""},
                    "PICO": {"host": "192.168.217.66", "port": 22, "username": "nav01", "password": ""},
                },
            }
            return new_sid, self.sessions[new_sid], True

    def touch(self, sid: str) -> None:
        if not sid:
            return
        with self.lock:
            session = self.sessions.get(sid)
            if session is not None:
                session["last_seen_ts"] = time.time()

    def get(self, sid: str | None) -> dict[str, Any] | None:
        normalized_sid = str(sid or "").strip()
        if not normalized_sid:
            return None
        with self.lock:
            return self.sessions.get(normalized_sid)

    def cleanup_expired(self, idle_timeout_seconds: int) -> int:
        timeout = max(1, int(idle_timeout_seconds or 0))
        now_ts = time.time()
        expired_sessions: list[dict[str, Any]] = []
        with self.lock:
            expired_ids = [
                sid
                for sid, session in self.sessions.items()
                if now_ts - float(session.get("last_seen_ts") or 0) >= timeout
            ]
            for sid in expired_ids:
                expired_sessions.append(self.sessions.pop(sid))
        for session in expired_sessions:
            self._release_session_resources(session)
        return len(expired_sessions)

    def close_all(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            self._release_session_resources(session)
