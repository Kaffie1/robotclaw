from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RouteOutput:
    route: str
    reason: str
    matched_playbook_id: str = ""


@dataclass
class ClassifyOutput:
    category: str
    summary: str
    detail: str


@dataclass
class ExecutionModeOutput:
    mode: str
    summary: str
    detail: str


@dataclass
class ToolPlanItem:
    tool_name: str
    reason: str


@dataclass
class ToolPlanOutput:
    category: str
    tools: list[ToolPlanItem] = field(default_factory=list)
    summary: str = ""


@dataclass
class SummaryOutput:
    summary: str
    evidence: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
