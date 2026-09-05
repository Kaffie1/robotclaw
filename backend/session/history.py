from __future__ import annotations

from dataclasses import asdict

from backend.memory.models import SessionMemory
from backend.shared.text import strip_image_attachment_summary


def build_preview(memory: SessionMemory) -> str:
    if not memory.chat_history:
        return "暂无消息"
    return strip_image_attachment_summary(memory.chat_history[-1].content).replace("\n", " ").strip()


def serialize_messages(memory: SessionMemory) -> list[dict]:
    messages = []
    for turn in memory.chat_history:
        message = asdict(turn)
        message["content"] = strip_image_attachment_summary(message.get("content", ""))
        images = message.get("metadata", {}).get("images", [])
        if images:
            message["images"] = images
        messages.append(message)
    return messages
