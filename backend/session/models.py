from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

InteractionMode = Literal["playbook", "qa", "agent"]


TaskStatus = Literal[
    "created",
    "running",
    "waiting_input",
    "waiting_confirm",
    "interrupted",
    "cancelled",
    "failed",
    "completed",
]


@dataclass
class UserIdentity:
    user_id: str
    username: str = ""


@dataclass
class TimestampSet:
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class SessionState:
    session_id: str
    user: UserIdentity
    current_task_id: str = ""
    current_robot_ref: str = ""
    interaction_mode: InteractionMode = "qa"
    status: TaskStatus = "created"
    active_topic: str = ""
    timestamps: TimestampSet = field(default_factory=TimestampSet)


@dataclass
class TaskState:
    task_id: str
    session_id: str
    title: str
    task_type: str
    status: TaskStatus = "created"
    current_node: str = ""
    error: str = ""
    retry_count: int = 0
    timestamps: TimestampSet = field(default_factory=TimestampSet)


@dataclass
class ChatTurn:
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: str = ""


def normalize_interaction_mode(value: str, default: InteractionMode = "qa") -> InteractionMode:
    normalized = str(value or "").strip().lower()
    if normalized in {"playbook", "qa", "agent"}:
        return normalized
    return default
