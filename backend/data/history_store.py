import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..core.time import now_text


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT,
                    task_id TEXT,
                    operation_type TEXT NOT NULL,
                    robot_host TEXT,
                    robot_port INTEGER,
                    robot_username TEXT,
                    title TEXT,
                    target_path TEXT,
                    remote_deb_path TEXT,
                    install_command TEXT,
                    start_command TEXT,
                    health_command TEXT,
                    rollback_command TEXT,
                    backup_path TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    logs TEXT,
                    created_at TEXT,
                    finished_at TEXT
                )
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(operation_history)").fetchall()}
            if "owner_id" not in columns:
                conn.execute("ALTER TABLE operation_history ADD COLUMN owner_id TEXT DEFAULT ''")

    def insert_entry(self, entry: dict[str, Any]) -> int:
        payload = {
            "owner_id": entry.get("owner_id", ""),
            "task_id": entry.get("task_id", ""),
            "operation_type": entry.get("operation_type", ""),
            "robot_host": entry.get("robot_host", ""),
            "robot_port": entry.get("robot_port"),
            "robot_username": entry.get("robot_username", ""),
            "title": entry.get("title", ""),
            "target_path": entry.get("target_path", ""),
            "remote_deb_path": entry.get("remote_deb_path", ""),
            "install_command": entry.get("install_command", ""),
            "start_command": entry.get("start_command", ""),
            "health_command": entry.get("health_command", ""),
            "rollback_command": entry.get("rollback_command", ""),
            "backup_path": entry.get("backup_path", ""),
            "status": entry.get("status", "succeeded"),
            "result_json": json.dumps(entry.get("result") or {}, ensure_ascii=False),
            "logs": "\n".join(entry.get("logs") or []),
            "created_at": entry.get("created_at", now_text()),
            "finished_at": entry.get("finished_at", now_text()),
        }
        with self.lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO operation_history (
                    owner_id, task_id, operation_type, robot_host, robot_port, robot_username, title,
                    target_path, remote_deb_path, install_command, start_command, health_command,
                    rollback_command, backup_path, status, result_json, logs, created_at, finished_at
                )
                VALUES (
                    :owner_id, :task_id, :operation_type, :robot_host, :robot_port, :robot_username, :title,
                    :target_path, :remote_deb_path, :install_command, :start_command, :health_command,
                    :rollback_command, :backup_path, :status, :result_json, :logs, :created_at, :finished_at
                )
                """,
                payload,
            )
            return int(cursor.lastrowid)

    def get_entry(self, entry_id: int, owner_id: str = "") -> dict[str, Any] | None:
        normalized_owner_id = str(owner_id or "")
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM operation_history WHERE id = ? AND owner_id = ?", (entry_id, normalized_owner_id)).fetchone()
        return self._serialize(row) if row else None

    def list_entries(self, limit: int = 20, owner_id: str = "") -> list[dict[str, Any]]:
        normalized_owner_id = str(owner_id or "")
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM operation_history WHERE owner_id = ? ORDER BY id DESC LIMIT ?", (normalized_owner_id, limit)).fetchall()
        return [self._serialize(row) for row in rows]

    def _serialize(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json") or "{}")
        item["logs"] = item["logs"].splitlines() if item.get("logs") else []
        item["rollback_available"] = bool(
            (item["operation_type"] == "deployment" and item.get("rollback_command"))
            or (item["operation_type"] == "file_replace" and item.get("backup_path"))
        )
        return item
