import inspect
import secrets
import threading
import traceback
from typing import Any

from ...core.config import MAX_TASK_ITEMS
from ...core.models import TaskFailure
from ...shared.runtime import now_text
from .history_store import HistoryStore


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
            progress.update({"done": False, "updated_at": now_text()})
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
