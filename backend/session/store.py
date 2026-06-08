from __future__ import annotations

from threading import RLock

from backend.session.models import SessionState, TaskState


class SessionStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, SessionState] = {}
        self._tasks: dict[str, TaskState] = {}
        self._session_order: list[str] = []

    def save_session(self, session: SessionState) -> None:
        with self._lock:
            self._sessions[session.session_id] = session
            if session.session_id not in self._session_order:
                self._session_order.insert(0, session.session_id)

    def save_task(self, task: TaskState) -> None:
        with self._lock:
            self._tasks[task.task_id] = task

    def get_session(self, session_id: str) -> SessionState:
        with self._lock:
            return self._sessions[session_id]

    def get_task(self, task_id: str) -> TaskState:
        with self._lock:
            return self._tasks[task_id]

    def has_task(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._tasks

    def list_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._session_order)

    def list_tasks_by_session(self, session_id: str) -> list[TaskState]:
        with self._lock:
            tasks = [task for task in self._tasks.values() if task.session_id == session_id]
            return sorted(tasks, key=lambda item: item.timestamps.created_at, reverse=True)

    def promote_session(self, session_id: str) -> None:
        with self._lock:
            self._session_order = [session_id] + [item for item in self._session_order if item != session_id]
