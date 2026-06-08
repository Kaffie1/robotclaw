from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.session.models import ChatTurn


@dataclass
class SessionMemory:
    session_id: str
    chat_history: list[ChatTurn] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    topic_stack: list[str] = field(default_factory=list)
    latest_summary: str = ""


@dataclass
class ShortMemory:
    task_id: str
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    rule_results: list[dict[str, Any]] = field(default_factory=list)
    visited_nodes: list[str] = field(default_factory=list)
    current_node: str = ""
    pending_confirmation: dict[str, Any] | None = None
    scratchpad: dict[str, Any] = field(default_factory=dict)


@dataclass
class LongMemoryRecord:
    memory_id: str
    category: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    source_session_id: str = ""
    source_task_id: str = ""
    created_at: str = ""
