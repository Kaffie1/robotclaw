from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.session.models import TaskStatus


@dataclass
class ChatRequest:
    session_id: str
    user_id: str
    content: str
    images: list[dict[str, Any]] = field(default_factory=list)
    request_id: str = ""
    interrupt: bool = False
    resume: bool = False


@dataclass
class ChatResponse:
    session_id: str
    task_id: str
    status: TaskStatus
    summary: str
    continuation_token: str = ""
    playbook_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
