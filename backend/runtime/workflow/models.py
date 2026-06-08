from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfirmationRequest:
    request_id: str
    session_id: str
    task_id: str
    node_path: str
    message: str
    options: list[str] = field(default_factory=list)
    resume_from_step: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResumeToken:
    token: str
    session_id: str
    task_id: str
    resume_from_step: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowEvent:
    event_id: str
    session_id: str
    task_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
