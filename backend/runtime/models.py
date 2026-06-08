from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.playbook.models import PlaybookExecutionState
from backend.session.models import SessionState, TaskState
from backend.ssh.models import RobotConnectionConfig
from backend.tools.models import PlannedToolCall, ToolExecutionResult


@dataclass
class RouteDecision:
    stage: str
    summary: str
    detail: str = ""


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
    trace: list[RouteDecision] = field(default_factory=list)
    tool_results: list[ToolExecutionResult] = field(default_factory=list)
    playbook_execution: PlaybookExecutionState = field(default_factory=PlaybookExecutionState)


@dataclass
class RuntimeEnvelope:
    session: SessionState
    task: TaskState
    diagnosis: DiagnosisSummary
    robot_config: RobotConnectionConfig
