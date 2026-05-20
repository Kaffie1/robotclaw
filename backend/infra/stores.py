import json
import secrets
import sqlite3
import threading
import time
import traceback
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import MAX_CONNECTION_CACHE_ITEMS, MAX_TASK_ITEMS
from ..core.models import TaskFailure
from .robot import RobotClient
from ..shared.runtime import now_text


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
    if not host or not username:
        return None
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


def normalize_machine_option(option: Any) -> dict[str, str] | None:
    if isinstance(option, dict):
        value = str(option.get("value") or option.get("id") or option.get("name") or "").strip()
        label = str(option.get("label") or option.get("title") or value).strip()
    else:
        value = str(option or "").strip()
        label = value
    if not value:
        return None
    return {"value": value, "label": label or value}


def normalize_doc_link(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    url = str(entry.get("url") or "").strip()
    if not title or not url:
        return None
    return {"title": title, "url": url}


def normalize_deploy_profile(profile: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    item = profile if isinstance(profile, dict) else {}
    probe_command_template = str(item.get("probe_command_template") or defaults.get("probe_command_template", "")).strip()
    install_template = str(item.get("install_template") or defaults["install_template"]).strip()
    if not install_template:
        install_template = defaults["install_template"]
    normalized = {
        "probe_command_template": probe_command_template,
        "up_wait_seconds": max(int(item.get("up_wait_seconds", defaults.get("up_wait_seconds", 0)) or 0), 0),
        "install_template": install_template,
        "start_command": str(item.get("start_command", defaults["start_command"])).strip(),
        "health_command": str(item.get("health_command", defaults["health_command"])).strip(),
        "rollback_template": str(item.get("rollback_template", defaults["rollback_template"])).strip(),
        "auto_rollback": bool(item.get("auto_rollback", defaults["auto_rollback"])),
    }
    raw_machine_options = item.get("machine_options", defaults.get("machine_options", []))
    machine_options: list[dict[str, str]] = []
    if isinstance(raw_machine_options, list):
        for option in raw_machine_options:
            normalized_option = normalize_machine_option(option)
            if normalized_option:
                machine_options.append(normalized_option)
    if machine_options:
        normalized["machine_options"] = machine_options
    raw_machine_profiles = item.get("machine_profiles", defaults.get("machine_profiles", {}))
    machine_profiles: dict[str, dict[str, Any]] = {}
    if isinstance(raw_machine_profiles, dict):
        for machine_key, machine_profile in raw_machine_profiles.items():
            normalized_key = str(machine_key or "").strip()
            machine_item = machine_profile if isinstance(machine_profile, dict) else {}
            if not normalized_key:
                continue
            machine_profiles[normalized_key] = {
                "probe_command_template": str(machine_item.get("probe_command_template", normalized["probe_command_template"])).strip(),
                "up_wait_seconds": max(int(machine_item.get("up_wait_seconds", normalized["up_wait_seconds"]) or 0), 0),
                "install_template": str(machine_item.get("install_template", normalized["install_template"])).strip()
                or normalized["install_template"],
                "start_command": str(machine_item.get("start_command", normalized["start_command"])).strip(),
                "health_command": str(machine_item.get("health_command", normalized["health_command"])).strip(),
                "rollback_template": str(machine_item.get("rollback_template", normalized["rollback_template"])).strip(),
                "auto_rollback": bool(machine_item.get("auto_rollback", normalized["auto_rollback"])),
            }
    if machine_profiles:
        normalized["machine_profiles"] = machine_profiles
    return normalized


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


class DeployConfigStore:
    def __init__(self, config_path: Path, defaults: dict[str, dict[str, Any]]) -> None:
        self.config_path = config_path
        self.defaults = defaults
        self.lock = threading.Lock()

    def ensure_exists(self) -> None:
        with self.lock:
            if not self.config_path.exists():
                self._write(self.defaults)

    def get_profile(self, deploy_mode: str = "package", machine_type: str = "", *, auto_select_default: bool = True) -> dict[str, Any]:
        """获取部署配置文件中指定部署模式和机型的配置，支持自动选择默认机型"""
        from ..core.models import ApiError

        mode = str(deploy_mode or "package").strip().lower()
        config = self.load()
        if mode not in config:
            raise ApiError(f"当前不支持的部署模式: {mode}")
        profile = config.get(mode)
        if profile is None:
            raise ApiError(f"部署配置中缺少 {mode} 配置")
        machine_options = profile.get("machine_options", [])
        option_values = [str(option.get("value") or "").strip() for option in machine_options if isinstance(option, dict)]
        resolved_machine_type = str(machine_type or "").strip()
        if auto_select_default and not resolved_machine_type and option_values:
            resolved_machine_type = option_values[0]
        resolved_profile = dict(profile)
        machine_profiles = profile.get("machine_profiles", {})
        if resolved_machine_type and isinstance(machine_profiles, dict):
            resolved_profile.update(machine_profiles.get(resolved_machine_type, {}))
        resolved_profile["machine_type"] = resolved_machine_type
        resolved_profile["deploy_mode"] = mode
        return resolved_profile

    def get_machine_options(self, deploy_mode: str = "package") -> list[dict[str, str]]:
        mode = str(deploy_mode or "package").strip().lower()
        profile = self.load().get(mode, {})
        options = profile.get("machine_options", [])
        return [option for option in options if isinstance(option, dict) and str(option.get("value") or "").strip()]

    def load(self) -> dict[str, dict[str, Any]]:
        from ..core.models import ApiError

        with self.lock:
            if not self.config_path.exists():
                self._write(self.defaults)
                return {key: dict(value) for key, value in self.defaults.items()}
            try:
                raw = self.config_path.read_text(encoding="utf-8")
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError as exc:
                raise ApiError(f"{self.config_path.name} 格式错误: {exc}") from exc
            except OSError as exc:
                raise ApiError(f"读取 {self.config_path.name} 失败: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ApiError(f"{self.config_path.name} 顶层必须是对象")
            return {key: normalize_deploy_profile(parsed.get(key), defaults) for key, defaults in self.defaults.items()}

    def _write(self, payload: dict[str, dict[str, Any]]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(f"{self.config_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.config_path)


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


class TaskContext:
    def __init__(self, manager: "TaskManager", task_id: str) -> None:
        self.manager = manager
        self.task_id = task_id

    def log(self, text: str) -> None:
        self.manager.append_log(self.task_id, text)


class TaskManager:
    def __init__(self, history_store: HistoryStore, max_items: int = MAX_TASK_ITEMS) -> None:
        self.history_store = history_store
        self.max_items = max(1, int(max_items or MAX_TASK_ITEMS))
        self.tasks: dict[str, dict[str, Any]] = {}
        self.upload_token_to_task_id: dict[str, str] = {}
        self.lock = threading.Lock()

    def create_task(self, task_type: str, title: str, metadata: dict[str, Any], runner, *, owner_id: str = "") -> dict[str, Any]:
        task_id = secrets.token_hex(8)
        task = {
            "id": task_id,
            "owner_id": str(owner_id or ""),
            "type": task_type,
            "title": title,
            "status": "pending",
            "metadata": metadata,
            "created_at": now_text(),
            "started_at": "",
            "finished_at": "",
            "logs": [],
            "result": {},
            "error": "",
            "history_id": None,
            "pending_confirmation": None,
            "resume_state": None,
            "progress": {
                "phase": "pending",
                "message": "任务已创建，等待后台执行",
                "percent": 0,
                "transferred_bytes": 0,
                "total_bytes": 0,
                "done": False,
                "error": "",
                "file_name": str(metadata.get("file_name") or metadata.get("package_file_name") or ""),
                "updated_at": now_text(),
            },
            "_runner": runner,
        }
        with self.lock:
            self.tasks[task_id] = task
            upload_token = str(metadata.get("upload_token") or "").strip()
            if upload_token:
                self.upload_token_to_task_id[upload_token] = task_id
            self._prune_tasks_locked()
        self.append_log(task_id, "任务已创建，等待后台执行")
        thread = threading.Thread(target=self._run_task, args=(task_id, runner, None), daemon=True)
        thread.start()
        return self.get_task(task_id) or {}

    def append_log(self, task_id: str, text: str) -> None:
        line = f"[{now_text()}] {text}"
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task["logs"].append(line)
            task["logs"] = task["logs"][-300:]

    def _invoke_runner(self, runner, context: TaskContext, continuation: dict[str, Any] | None = None):
        try:
            parameter_count = len(inspect.signature(runner).parameters)
        except (TypeError, ValueError):
            parameter_count = 1
        if parameter_count >= 2:
            return runner(context, continuation)
        return runner(context)

    def _run_task(self, task_id: str, runner, continuation: dict[str, Any] | None = None) -> None:
        update_payload = {"status": "running", "pending_confirmation": None, "resume_state": None}
        if not continuation:
            update_payload["started_at"] = now_text()
        self._update_task(task_id, update_payload)
        context = TaskContext(self, task_id)
        context.log("任务开始执行" if not continuation else "任务继续执行")
        payload: dict[str, Any] = {}
        status = "succeeded"
        error = ""
        try:
            result = self._invoke_runner(runner, context, continuation)
            payload = result if isinstance(result, dict) else {"summary": result}
            pending_confirmation = payload.get("pending_confirmation") if isinstance(payload.get("pending_confirmation"), dict) else None
            resume_state = payload.get("resume_state") if isinstance(payload.get("resume_state"), dict) else None
            if pending_confirmation and resume_state:
                context.log(f"任务等待确认: {str(pending_confirmation.get('message') or '').strip()}")
                self._pause_task(task_id, payload, pending_confirmation, resume_state)
                return
            summary = payload.get("summary", payload) if isinstance(payload, dict) else {}
            context.log(
                "任务执行器返回，准备收口状态: "
                f"summary_type={type(summary).__name__}, "
                f"warnings={len(summary.get('warnings') or []) if isinstance(summary, dict) else 0}"
            )
            if isinstance(summary, dict) and summary.get("warnings"):
                status = "warning"
                context.log(f"任务完成，但存在 {len(summary.get('warnings') or [])} 条告警")
        except TaskFailure as exc:
            status = "failed"
            error = str(exc)
            payload = exc.payload
            context.log(f"任务失败: {error}")
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            context.log(f"任务异常: {error}")
            context.log(traceback.format_exc())
        context.log(f"任务状态即将写入: {status}")
        self._finish_task(task_id, status, payload, error)

    def _pause_task(
        self,
        task_id: str,
        payload: dict[str, Any],
        pending_confirmation: dict[str, Any],
        resume_state: dict[str, Any],
    ) -> None:
        result = payload.get("summary", payload) if isinstance(payload, dict) else {}
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task["status"] = "waiting_confirmation"
            task["result"] = result
            task["pending_confirmation"] = pending_confirmation
            task["resume_state"] = resume_state
            task["error"] = ""
            progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
            progress.update(
                {
                    "done": False,
                    "updated_at": now_text(),
                }
            )
            task["progress"] = progress

    def continue_task(self, task_id: str, confirmation_response: str, *, owner_id: str = "") -> dict[str, Any] | None:
        normalized_owner_id = str(owner_id or "")
        with self.lock:
            task = self.tasks.get(task_id)
            if (
                not task
                or str(task.get("owner_id") or "") != normalized_owner_id
                or str(task.get("status") or "") != "waiting_confirmation"
            ):
                return None
            runner = task.get("_runner")
            pending_confirmation = task.get("pending_confirmation")
            resume_state = task.get("resume_state")
        if not runner or not isinstance(pending_confirmation, dict) or not isinstance(resume_state, dict):
            return None
        continuation = {
            "confirmation_response": str(confirmation_response or "").strip(),
            "pending_confirmation": pending_confirmation,
            "resume_state": resume_state,
        }
        self.append_log(task_id, f"收到确认输入: {continuation['confirmation_response']}")
        thread = threading.Thread(target=self._run_task, args=(task_id, runner, continuation), daemon=True)
        thread.start()
        return self.get_task(task_id)

    def _finish_task(self, task_id: str, status: str, payload: dict[str, Any], error: str) -> None:
        result = payload.get("summary", payload) if isinstance(payload, dict) else {}
        history_payload = payload.get("history") if isinstance(payload, dict) else None
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task["status"] = status
            task["finished_at"] = now_text()
            task["result"] = result
            task["error"] = error
            progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
            progress.setdefault("file_name", str(task.get("metadata", {}).get("file_name") or task.get("metadata", {}).get("package_file_name") or ""))
            progress["done"] = True
            progress["updated_at"] = now_text()
            if status == "failed":
                progress["phase"] = "failed"
                progress["error"] = error
                progress["message"] = error or str(progress.get("message") or "任务执行失败")
            else:
                progress["phase"] = "completed"
                progress["error"] = ""
                progress["percent"] = 100 if int(progress.get("total_bytes") or 0) > 0 else int(progress.get("percent") or 0)
                progress["message"] = str(progress.get("message") or ("任务完成" if status == "succeeded" else "任务完成（有告警）"))
            task["progress"] = progress
            logs = list(task["logs"])
            task_snapshot = dict(task)
        if history_payload:
            history_entry = {
                **history_payload,
                "owner_id": str(task_snapshot.get("owner_id") or ""),
                "task_id": task_id,
                "status": status,
                "result": result,
                "logs": logs,
                "created_at": task_snapshot["created_at"],
                "finished_at": task_snapshot["finished_at"],
            }
            history_id = self.history_store.insert_entry(history_entry)
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id]["history_id"] = history_id
                self._prune_tasks_locked()

    def _update_task(self, task_id: str, values: dict[str, Any]) -> None:
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.update(values)

    def sync_progress_from_upload(self, token: str, progress: dict[str, Any]) -> None:
        normalized_token = str(token or "").strip()
        if not normalized_token or not isinstance(progress, dict):
            return
        with self.lock:
            task_id = self.upload_token_to_task_id.get(normalized_token)
            if not task_id:
                return
            task = self.tasks.get(task_id)
            if not task:
                self.upload_token_to_task_id.pop(normalized_token, None)
                return
            task["progress"] = {
                "phase": str(progress.get("phase") or "").strip(),
                "message": str(progress.get("message") or "").strip(),
                "step_name": str(progress.get("step_name") or "").strip(),
                "step_label": str(progress.get("step_label") or "").strip(),
                "percent": float(progress.get("percent") or 0),
                "transferred_bytes": int(progress.get("transferred_bytes") or 0),
                "total_bytes": int(progress.get("total_bytes") or 0),
                "done": bool(progress.get("done")),
                "error": str(progress.get("error") or "").strip(),
                "file_name": str(progress.get("file_name") or task.get("metadata", {}).get("file_name") or task.get("metadata", {}).get("package_file_name") or "").strip(),
                "updated_at": str(progress.get("updated_at") or now_text()),
            }

    def list_tasks(self, limit: int = MAX_TASK_ITEMS) -> list[dict[str, Any]]:
        with self.lock:
            items = sorted(self.tasks.values(), key=lambda item: (item["created_at"], item["id"]), reverse=True)
        return [self._serialize_task(task, include_logs=False) for task in items[:limit]]

    def list_tasks_for_owner(self, owner_id: str, limit: int = MAX_TASK_ITEMS) -> list[dict[str, Any]]:
        normalized_owner_id = str(owner_id or "")
        with self.lock:
            items = [
                item
                for item in sorted(self.tasks.values(), key=lambda item: (item["created_at"], item["id"]), reverse=True)
                if str(item.get("owner_id") or "") == normalized_owner_id
            ]
        return [self._serialize_task(task, include_logs=False) for task in items[:limit]]

    def _prune_tasks_locked(self) -> None:
        """删除最早的任务，直到任务数量不超过 max_items"""
        if len(self.tasks) <= self.max_items:
            return
        ordered_ids = [item["id"] for item in sorted(self.tasks.values(), key=lambda item: (item["created_at"], item["id"]))]
        for task_id in ordered_ids[: len(self.tasks) - self.max_items]:
            self.tasks.pop(task_id, None)
            stale_tokens = [token for token, mapped_task_id in self.upload_token_to_task_id.items() if mapped_task_id == task_id]
            for token in stale_tokens:
                self.upload_token_to_task_id.pop(token, None)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            return self._serialize_task(task, include_logs=True)

    def get_task_for_owner(self, task_id: str, owner_id: str) -> dict[str, Any] | None:
        normalized_owner_id = str(owner_id or "")
        with self.lock:
            task = self.tasks.get(task_id)
            if not task or str(task.get("owner_id") or "") != normalized_owner_id:
                return None
            return self._serialize_task(task, include_logs=True)

    def _serialize_task(self, task: dict[str, Any], include_logs: bool) -> dict[str, Any]:
        return {
            "id": task["id"],
            "type": task["type"],
            "title": task["title"],
            "status": task["status"],
            "metadata": task["metadata"],
            "created_at": task["created_at"],
            "started_at": task["started_at"],
            "finished_at": task["finished_at"],
            "result": task["result"],
            "error": task["error"],
            "history_id": task["history_id"],
            "pending_confirmation": task.get("pending_confirmation"),
            "progress": dict(task.get("progress") or {}),
            "logs": list(task["logs"]) if include_logs else [],
        }


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
                "client": RobotClient(),
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


class UploadProgressManager:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.update_callback = None

    def set_update_callback(self, callback) -> None:
        self.update_callback = callback

    def start(
        self,
        token: str,
        *,
        file_name: str = "",
        total_bytes: int = 0,
        phase: str = "pending",
        message: str = "",
        owner_id: str = "",
        step_name: str = "",
        step_label: str = "",
    ) -> None:
        """使用一个唯一的 token 来标识上传任务，并初始化其进度信息。"""
        if not token:
            return
        with self.lock:
            self.items[token] = {
                "token": token,
                "owner_id": str(owner_id or ""),
                "file_name": file_name,
                "phase": phase,
                "message": message,
                "step_name": step_name,
                "step_label": step_label,
                "total_bytes": total_bytes,
                "transferred_bytes": 0,
                "percent": 0,
                "done": False,
                "error": "",
                "updated_at": now_text(),
            }
            snapshot = dict(self.items[token])
        if callable(self.update_callback):
            self.update_callback(token, snapshot)

    def update(
        self,
        token: str,
        *,
        transferred_bytes: int | None = None,
        total_bytes: int | None = None,
        phase: str | None = None,
        message: str | None = None,
        done: bool | None = None,
        error: str | None = None,
        owner_id: str = "",
        step_name: str | None = None,
        step_label: str | None = None,
    ) -> None:
        if not token:
            return
        with self.lock:
            item = self.items.get(token)
            if item is None:
                self.start(token, owner_id=owner_id)
                item = self.items[token]
            if transferred_bytes is not None:
                item["transferred_bytes"] = transferred_bytes
            if total_bytes is not None:
                item["total_bytes"] = total_bytes
            if phase is not None:
                item["phase"] = phase
            if message is not None:
                item["message"] = message
            if step_name is not None:
                item["step_name"] = step_name
            if step_label is not None:
                item["step_label"] = step_label
            if done is not None:
                item["done"] = done
            if error is not None:
                item["error"] = error
            total = int(item.get("total_bytes") or 0)
            transferred = int(item.get("transferred_bytes") or 0)
            item["percent"] = round((transferred / total) * 100, 2) if total > 0 else 0
            item["updated_at"] = now_text()
            snapshot = dict(item)
        if callable(self.update_callback):
            self.update_callback(token, snapshot)

    def fail(self, token: str, message: str, owner_id: str = "") -> None:
        self.update(token, phase="failed", message=message, error=message, done=True, owner_id=owner_id)

    def get(self, token: str, owner_id: str = "") -> dict[str, Any] | None:
        if not token:
            return None
        normalized_owner_id = str(owner_id or "")
        with self.lock:
            item = self.items.get(token)
            if not item or str(item.get("owner_id") or "") != normalized_owner_id:
                return None
            snapshot = dict(item)
        return snapshot
