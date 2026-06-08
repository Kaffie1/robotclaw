from __future__ import annotations

from threading import RLock

from backend.memory.models import LongMemoryRecord, SessionMemory, ShortMemory


class MemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._session_memory: dict[str, SessionMemory] = {}
        self._short_memory: dict[str, ShortMemory] = {}
        self._long_memory: dict[str, list[LongMemoryRecord]] = {}

    def ensure_session_memory(self, session_id: str) -> SessionMemory:
        with self._lock:
            return self._session_memory.setdefault(session_id, SessionMemory(session_id=session_id))

    def ensure_short_memory(self, task_id: str) -> ShortMemory:
        with self._lock:
            return self._short_memory.setdefault(task_id, ShortMemory(task_id=task_id))

    def append_long_memory(self, session_id: str, record: LongMemoryRecord) -> None:
        with self._lock:
            self._long_memory.setdefault(session_id, []).append(record)

    def list_long_memory(self, session_id: str) -> list[LongMemoryRecord]:
        with self._lock:
            return list(self._long_memory.get(session_id, []))
