from __future__ import annotations

from dataclasses import asdict

from backend.memory.models import SessionMemory


def build_preview(memory: SessionMemory) -> str:
    if not memory.chat_history:
        return "暂无消息"
    return memory.chat_history[-1].content.replace("\n", " ").strip()


def serialize_messages(memory: SessionMemory) -> list[dict]:
    return [asdict(turn) for turn in memory.chat_history]
