from __future__ import annotations

from backend.tools import ToolExecutor
from backend.tools.models import PlannedToolCall


def plan_tools(tool_executor: ToolExecutor, category: str, connected: bool) -> list[PlannedToolCall]:
    return tool_executor.plan(category, connected)


def summarize_tool_plan(planned_tools: list[PlannedToolCall]) -> str:
    if not planned_tools:
        return "当前无需工具调用"
    if len(planned_tools) == 1 and planned_tools[0].tool_name == "connect_robot":
        return "需要先连接机器人后再执行诊断"
    names = ", ".join(call.tool_name for call in planned_tools)
    return f"已生成 {len(planned_tools)} 个候选工具动作：{names}"
