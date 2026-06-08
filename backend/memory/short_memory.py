from __future__ import annotations

from backend.memory.models import ShortMemory
from backend.memory.store import MemoryStore


class ShortMemoryService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def ensure(self, task_id: str) -> ShortMemory:
        return self.store.ensure_short_memory(task_id)
