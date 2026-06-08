from __future__ import annotations

from backend.memory.models import LongMemoryRecord
from backend.memory.store import MemoryStore


class LongMemoryService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def append(self, session_id: str, record: LongMemoryRecord) -> None:
        self.store.append_long_memory(session_id, record)

    def list(self, session_id: str) -> list[LongMemoryRecord]:
        return self.store.list_long_memory(session_id)
