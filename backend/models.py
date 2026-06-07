from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
class ChatRequest:
    session_id: str
    user_id: str
    content: str
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


@dataclass
class SessionState:
    session_id: str
    user: UserIdentity
    current_task_id: str = ""
    current_robot_ref: str = ""
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


@dataclass
class SessionMemory:
    session_id: str
    chat_history: list[ChatTurn] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedToolCall:
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeState:
    session_id: str
    task_id: str
    user_query: str
    route: str = ""
    matched_playbook_id: str = ""
    current_step: str = ""
    planned_tools: list[PlannedToolCall] = field(default_factory=list)
    retrieval_result: Any = None
    knowledge_used: bool = False
    knowledge_confidence: float = 0.0
    knowledge_low_confidence: bool = False
    interrupt_flag: bool = False
    resume_token: str = ""
    resume_from_step: str = ""
    finished: bool = False


@dataclass
class RobotConnectionConfig:
    robot_ref: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    private_key_path: str = ""
    ros_version: str = ""
    workspace: str = ""
    setup_script: str = ""


@dataclass
class SSHConnectionState:
    connected: bool = False
    robot_ref: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    last_error: str = ""
    connected_at: str = ""


@dataclass
class EvidenceItem:
    source: str
    content: str
    confidence: float = 0.0


@dataclass
class SolutionItem:
    title: str
    detail: str
    auto_fix: bool = False


@dataclass
class DiagnosisSummary:
    evidence: list[EvidenceItem] = field(default_factory=list)
    solutions: list[SolutionItem] = field(default_factory=list)
    final_answer: str = ""


@dataclass
class RuntimeEnvelope:
    session: SessionState
    task: TaskState
    diagnosis: DiagnosisSummary
    robot_config: RobotConnectionConfig
