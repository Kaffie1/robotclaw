from __future__ import annotations

from backend.tools import ToolExecutor
from backend.tools.models import ToolCall, ToolResult
from backend.runtime.models import EvidenceItem, RouteDecision


def check_robot(
    tool_executor: ToolExecutor,
    planned_tools: list[ToolCall],
    connected: bool,
) -> list[ToolResult]:
    return tool_executor.execute(planned_tools, connected)


def check_robot_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    tool_executor = state["tool_executor"]

    runtime_state.current_step = "robot_check"
    runtime_state.tool_results = check_robot(tool_executor, runtime_state.planned_tools, state["connected"])
    short_memory.tool_results = tool_executor.to_payload(runtime_state.tool_results)
    short_memory.current_node = "robot_check"
    runtime_state.trace.append(
        RouteDecision(
            stage="工具执行",
            summary=_tool_execution_summary(runtime_state.tool_results),
            detail="；".join(str(item.get("summary", "")).strip() for item in runtime_state.tool_results) or "暂无执行结果",
        )
    )
    diagnosis.evidence.extend(
        EvidenceItem(source="tool", content=str(item.get("summary", "")).strip(), confidence=0.9 if item.get("success") else 0.4)
        for item in runtime_state.tool_results
    )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
    }


def _tool_execution_summary(results: list[ToolResult]) -> str:
    if not results:
        return "当前没有执行任何工具动作"
    completed = sum(1 for item in results if item.get("success"))
    blocked = sum(1 for item in results if not item.get("success"))
    return f"已完成 {completed} 个工具动作，阻塞 {blocked} 个动作"
