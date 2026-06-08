from __future__ import annotations

from backend.tools import ToolExecutor
from backend.tools.models import PlannedToolCall, ToolExecutionResult


def check_robot(
    tool_executor: ToolExecutor,
    planned_tools: list[PlannedToolCall],
    connected: bool,
) -> list[ToolExecutionResult]:
    return tool_executor.execute(planned_tools, connected)
