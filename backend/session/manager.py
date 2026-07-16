from __future__ import annotations

from threading import RLock

from backend.memory import MemoryManager
from backend.memory.models import SessionMemory
from backend.session.history import build_preview, serialize_messages
from backend.session.models import ChatTurn, SessionState, TaskState, TimestampSet, UserIdentity, normalize_interaction_mode
from backend.session.store import SessionStore
from backend.shared import DEFAULT_INTERACTION_MODE, infer_title, next_session_id, next_task_id, now_hhmm, now_iso
from backend.shared.question_log import append_question


class SessionManager:
    def __init__(self, memory_manager: MemoryManager | None = None) -> None:
        self._lock = RLock()
        self._memory_manager = memory_manager or MemoryManager()
        self._store = SessionStore()

    def create_session(self, user: UserIdentity, title: str | None = None, interaction_mode: str | None = None) -> SessionState:
        with self._lock:
            session_id = next_session_id()
            timestamps = TimestampSet(created_at=now_iso(), updated_at=now_iso())
            session = SessionState(
                session_id=session_id,
                user=user,
                interaction_mode=normalize_interaction_mode(interaction_mode or DEFAULT_INTERACTION_MODE),
                status="created",
                active_topic=title or "",
                timestamps=timestamps,
            )
            self._store.save_session(session)
            self._memory_manager.ensure_session_memory(session_id)
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
            self._store.save_task(task)
            session = self._store.get_session(session_id)
            session.current_task_id = task_id
            session.status = "created"
            session.timestamps.updated_at = now_iso()
            self._store.save_session(session)
            return task

    def ensure_active_task(self, session_id: str, title: str) -> TaskState:
        with self._lock:
            session = self._store.get_session(session_id)
            if session.current_task_id and self._store.has_task(session.current_task_id):
                return self._store.get_task(session.current_task_id)
            return self.create_task(session_id, title=title, task_type="diagnose")

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            memory = self._memory_manager.get_session_memory(session_id)
            memory.chat_history.append(ChatTurn(role=role, content=content, created_at=now_hhmm()))
            memory.latest_summary = content.replace("\n", " ").strip()[:120]
            if role == "user":
                append_question(session_id, content)
                memory.topic_stack.append(content.strip()[:80])
                memory.topic_stack = memory.topic_stack[-10:]
            session = self._store.get_session(session_id)
            session.timestamps.updated_at = now_iso()
            self._store.save_session(session)
            self._move_to_front(session_id)

    def update_interaction_mode(self, session_id: str, interaction_mode: str) -> SessionState:
        with self._lock:
            session = self._store.get_session(session_id)
            session.interaction_mode = normalize_interaction_mode(interaction_mode, default=session.interaction_mode)
            session.timestamps.updated_at = now_iso()
            self._store.save_session(session)
            return session

    def update_session_from_chat(self, session_id: str, title_seed: str) -> None:
        with self._lock:
            session = self._store.get_session(session_id)
            if not session.active_topic:
                session.active_topic = title_seed
            if session.current_task_id and self._store.has_task(session.current_task_id):
                task = self._store.get_task(session.current_task_id)
                task.title = infer_title(title_seed, task.title)
                task.timestamps.updated_at = now_iso()
                self._store.save_task(task)
            self._store.save_session(session)
            self._touch_session_preview(session_id)

    def set_task_status(self, task_id: str, status: str, current_node: str = "", error: str = "") -> None:
        with self._lock:
            task = self._store.get_task(task_id)
            task.status = status
            task.current_node = current_node
            task.error = error
            task.timestamps.updated_at = now_iso()
            if status == "running" and not task.timestamps.started_at:
                task.timestamps.started_at = now_iso()
            if status in {"completed", "failed", "cancelled"}:
                task.timestamps.finished_at = now_iso()
            self._store.save_task(task)

            session = self._store.get_session(task.session_id)
            session.status = status
            session.timestamps.updated_at = now_iso()
            self._store.save_session(session)

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [self.session_payload(session_id) for session_id in self._store.list_session_ids()]

    def get_session_state(self, session_id: str) -> SessionState:
        return self._store.get_session(session_id)

    def get_task_state(self, task_id: str) -> TaskState:
        return self._store.get_task(task_id)

    def get_memory(self, session_id: str) -> SessionMemory:
        return self._memory_manager.get_session_memory(session_id)

    def bootstrap_payload(self) -> dict:
        session_ids = self._store.list_session_ids()
        return {
            "sessions": self.list_sessions(),
            "active_session_id": session_ids[0] if session_ids else "",
        }

    def create_session_payload(self, user_id: str, interaction_mode: str | None = None) -> dict:
        user = UserIdentity(user_id=user_id, username=user_id)
        session = self.create_session(user, interaction_mode=interaction_mode)
        task = self.create_task(session.session_id, "新会话", task_type="diagnose")
        self.record_turn(session.session_id, "assistant", "新的会话已创建。你可以直接输入机器人问题，或先连接右侧机器人。")
        self.set_task_status(task.task_id, "created")
        self.update_session_from_chat(session.session_id, "新会话")
        return {
            "session": self.session_payload(session.session_id),
            "active_session_id": session.session_id,
        }

    def session_payload(self, session_id: str) -> dict:
        session = self._store.get_session(session_id)
        memory = self._memory_manager.get_session_memory(session_id)
        return {
            "id": session.session_id,
            "title": session.active_topic or "新会话",
            "preview": build_preview(memory),
            "messages": serialize_messages(memory),
            "interaction_mode": session.interaction_mode,
        }

    def history_payload(self, session_id: str) -> dict:
        session = self._store.get_session(session_id)
        tasks = self._store.list_tasks_by_session(session_id)
        return {
            "session": self.session_payload(session_id),
            "task_history": [
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "task_type": task.task_type,
                    "status": task.status,
                    "current_node": task.current_node,
                    "error": task.error,
                    "created_at": task.timestamps.created_at,
                    "updated_at": task.timestamps.updated_at,
                    "started_at": task.timestamps.started_at,
                    "finished_at": task.timestamps.finished_at,
                }
                for task in tasks
            ],
            "active_task_id": session.current_task_id,
        }

    def _touch_session_preview(self, session_id: str) -> None:
        self._move_to_front(session_id)

    def _preview_for(self, session_id: str) -> str:
        return build_preview(self._memory_manager.get_session_memory(session_id))

    def _move_to_front(self, session_id: str) -> None:
        self._store.promote_session(session_id)
