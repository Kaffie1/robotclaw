from __future__ import annotations

from backend.memory.long_memory import LongMemoryService
from backend.memory.models import LongMemoryRecord, SessionMemory, ShortMemory
from backend.memory.session_memory import SessionMemoryService
from backend.memory.short_memory import ShortMemoryService
from backend.memory.store import MemoryStore


class MemoryManager:
    def __init__(self) -> None:
        self._store = MemoryStore()
        self._session = SessionMemoryService(self._store)
        self._short = ShortMemoryService(self._store)
        self._long = LongMemoryService(self._store)

    def ensure_session_memory(self, session_id: str) -> SessionMemory:
        return self._session.ensure(session_id)

    def get_session_memory(self, session_id: str) -> SessionMemory:
        return self.ensure_session_memory(session_id)

    def ensure_short_memory(self, task_id: str) -> ShortMemory:
        return self._short.ensure(task_id)

    def get_short_memory(self, task_id: str) -> ShortMemory:
        return self.ensure_short_memory(task_id)

    def append_long_memory(self, session_id: str, record: LongMemoryRecord) -> None:
        self._long.append(session_id, record)

    def list_long_memory(self, session_id: str) -> list[LongMemoryRecord]:
        return self._long.list(session_id)
