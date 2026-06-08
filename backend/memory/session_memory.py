from __future__ import annotations

from backend.memory.models import SessionMemory
from backend.memory.store import MemoryStore


class SessionMemoryService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def ensure(self, session_id: str) -> SessionMemory:
        return self.store.ensure_session_memory(session_id)
