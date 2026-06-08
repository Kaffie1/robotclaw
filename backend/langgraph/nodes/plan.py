from __future__ import annotations

from backend.llm import parse_tool_plan_output
from backend.tools import ToolExecutor
from backend.tools.models import PlannedToolCall
from backend.runtime.models import RouteDecision


def plan_tools(tool_executor: ToolExecutor, category: str, connected: bool) -> list[PlannedToolCall]:
    return tool_executor.plan(category, connected)


def summarize_tool_plan(planned_tools: list[PlannedToolCall]) -> str:
    if not planned_tools:
        return "当前无需工具调用"
    if len(planned_tools) == 1 and planned_tools[0].tool_name == "connect_robot":
        return "需要先连接机器人后再执行诊断"
    names = ", ".join(call.tool_name for call in planned_tools)
    return f"已生成 {len(planned_tools)} 个候选工具动作：{names}"


def plan_tools_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    intent = state["intent"]
    request = state["request"]

    runtime_state.current_step = "tool_planning"
    prompt = state["build_planner_prompt"](request.content, runtime_state.route)
    short_memory.scratchpad["planner_prompt"] = prompt
    runtime_state.planned_tools = plan_tools(state["tool_executor"], intent["category"], state["connected"])
    try:
        response = state["llm_client"].invoke_schema(
            prompt=prompt,
            schema_parser=parse_tool_plan_output,
            metadata={"node": "plan"},
        )
        planned_from_llm = plan_tools(state["tool_executor"], response.parsed["category"], state["connected"])
        if planned_from_llm:
            runtime_state.planned_tools = planned_from_llm
            short_memory.scratchpad["planner_result"] = response.parsed
    except Exception:
        pass
    runtime_state.trace.append(
        RouteDecision(
            stage="工具规划",
            summary=summarize_tool_plan(runtime_state.planned_tools),
            detail=" -> ".join(call.tool_name for call in runtime_state.planned_tools) if runtime_state.planned_tools else "暂无工具计划",
        )
    )
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
    }
