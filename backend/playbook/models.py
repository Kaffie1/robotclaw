from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


BTNodeType = Literal["sequence", "selector", "condition", "action", "input", "result", "call_playbook"]


@dataclass
class PlaybookMeta:
    playbook_id: str
    name: str
    version: str = "v1"
    category: str = "fault"
    description: str = ""


@dataclass
class ConditionRuleRef:
    rule_id: str
    inputs: dict[str, str] = field(default_factory=dict)
    expected: bool = True


@dataclass
class BTNodeSpec:
    node_id: str
    node_type: BTNodeType
    name: str
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    rule: ConditionRuleRef | None = None
    prompt: str = ""
    children: list["BTNodeSpec"] = field(default_factory=list)
    success_message: str = ""
    failure_message: str = ""


@dataclass
class PlaybookSpec:
    meta: PlaybookMeta
    root: BTNodeSpec
    input_fields: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class PlaybookExecutionState:
    playbook_id: str = ""
    current_node_id: str = ""
    completed_nodes: list[str] = field(default_factory=list)
    failed_nodes: list[str] = field(default_factory=list)
    waiting_input_field: str = ""
    passed: bool | None = None


@dataclass
class BlackboardSnapshot:
    current_node_id: str = ""
    observations: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    tool_outputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterruptState:
    interrupted: bool = False
    reason: str = ""
    current_node_id: str = ""
    blackboard: BlackboardSnapshot | None = None


@dataclass
class NodeExecutionResult:
    node_id: str
    status: Literal["success", "failure", "running", "interrupted"]
    output: dict[str, Any] = field(default_factory=dict)
    rule_result: dict[str, Any] | None = None
    message: str = ""
