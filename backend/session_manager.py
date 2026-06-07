from __future__ import annotations

from dataclasses import asdict
from threading import RLock

from backend.common import infer_title, next_session_id, next_task_id, now_hhmm, now_iso
from backend.models import ChatTurn, SessionMemory, SessionState, TaskState, TimestampSet, UserIdentity


class SessionManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, SessionState] = {}
        self._tasks: dict[str, TaskState] = {}
        self._memory: dict[str, SessionMemory] = {}
        self._session_order: list[str] = []
        self._bootstrap_default_session()

    def _bootstrap_default_session(self) -> None:
        user = UserIdentity(user_id="u001", username="default")
        session = self.create_session(user, title="导航问题诊断")
        memory = self._memory[session.session_id]
        task = self.create_task(session.session_id, "导航问题诊断", task_type="diagnose")
        session.current_task_id = task.task_id
        session.active_topic = "导航问题诊断"
        self._touch_session_preview(session.session_id)

    def create_session(self, user: UserIdentity, title: str | None = None) -> SessionState:
        with self._lock:
            session_id = next_session_id()
            timestamps = TimestampSet(created_at=now_iso(), updated_at=now_iso())
            session = SessionState(
                session_id=session_id,
                user=user,
                status="created",
                active_topic=title or "",
                timestamps=timestamps,
            )
            self._sessions[session_id] = session
            self._memory[session_id] = SessionMemory(session_id=session_id)
            self._session_order.insert(0, session_id)
            return session

    def create_task(self, session_id: str, title: str, task_type: str) -> TaskState:
        with self._lock:
            task_id = next_task_id()
            timestamps = TimestampSet(created_at=now_iso(), updated_at=now_iso())
            task = TaskState(
                task_id=task_id,
                session_id=session_id,
                title=title,
                task_type=task_type,
                status="created",
                timestamps=timestamps,
            )
            self._tasks[task_id] = task
            session = self._sessions[session_id]
            session.current_task_id = task_id
            session.status = "created"
            session.timestamps.updated_at = now_iso()
            return task

    def ensure_active_task(self, session_id: str, title: str) -> TaskState:
        with self._lock:
            session = self._sessions[session_id]
            if session.current_task_id and session.current_task_id in self._tasks:
                return self._tasks[session.current_task_id]
            return self.create_task(session_id, title=title, task_type="diagnose")

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            memory = self._memory[session_id]
            memory.chat_history.append(ChatTurn(role=role, content=content, created_at=now_hhmm()))
            session = self._sessions[session_id]
            session.timestamps.updated_at = now_iso()
            self._move_to_front(session_id)

    def update_session_from_chat(self, session_id: str, title_seed: str) -> None:
        with self._lock:
            session = self._sessions[session_id]
            if not session.active_topic:
                session.active_topic = title_seed
            if session.current_task_id in self._tasks:
                task = self._tasks[session.current_task_id]
                task.title = infer_title(title_seed, task.title)
                task.timestamps.updated_at = now_iso()
            self._touch_session_preview(session_id)

    def set_task_status(self, task_id: str, status: str, current_node: str = "", error: str = "") -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = status
            task.current_node = current_node
            task.error = error
            task.timestamps.updated_at = now_iso()
            if status == "running" and not task.timestamps.started_at:
                task.timestamps.started_at = now_iso()
            if status in {"completed", "failed", "cancelled"}:
                task.timestamps.finished_at = now_iso()

            session = self._sessions[task.session_id]
            session.status = status
            session.timestamps.updated_at = now_iso()

    def list_sessions(self) -> list[dict]:
        with self._lock:
            result: list[dict] = []
            for session_id in self._session_order:
                session = self._sessions[session_id]
                preview = self._preview_for(session_id)
                result.append(
                    {
                        "id": session.session_id,
                        "title": session.active_topic or "新会话",
                        "preview": preview,
                        "messages": [asdict(turn) for turn in self._memory[session_id].chat_history],
                    }
                )
            return result

    def get_session_state(self, session_id: str) -> SessionState:
        return self._sessions[session_id]

    def get_task_state(self, task_id: str) -> TaskState:
        return self._tasks[task_id]

    def get_memory(self, session_id: str) -> SessionMemory:
        return self._memory[session_id]

    def bootstrap_payload(self) -> dict:
        sessions = self.list_sessions()
        active_session_id = self._session_order[0] if self._session_order else ""
        return {
            "sessions": sessions,
            "active_session_id": active_session_id,
        }

    def create_session_payload(self, user_id: str) -> dict:
        user = UserIdentity(user_id=user_id, username=user_id)
        session = self.create_session(user)
        task = self.create_task(session.session_id, "新会话", task_type="diagnose")
        self.record_turn(session.session_id, "assistant", "新的会话已创建。你可以直接输入机器人问题，或先连接右侧机器人。")
        self.set_task_status(task.task_id, "created")
        self.update_session_from_chat(session.session_id, "新会话")
        return {
            "session": self.list_sessions()[0],
            "active_session_id": session.session_id,
        }

    def _touch_session_preview(self, session_id: str) -> None:
        self._move_to_front(session_id)

    def _preview_for(self, session_id: str) -> str:
        history = self._memory[session_id].chat_history
        if not history:
            return "暂无消息"
        return history[-1].content.replace("\n", " ").strip()

    def _move_to_front(self, session_id: str) -> None:
        self._session_order = [session_id] + [item for item in self._session_order if item != session_id]
