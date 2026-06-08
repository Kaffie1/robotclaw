from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlannedToolCall:
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionResult:
    tool_name: str
    status: str
    facts: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
