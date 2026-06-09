from __future__ import annotations

from backend.llm import parse_tool_plan_output
from backend.tools import ToolExecutor
from backend.tools.models import ToolCall
from backend.runtime.models import RouteDecision


def plan_tools(
    tool_executor: ToolExecutor,
    suggested_tools: list[str],
    connected: bool,
    *,
    session_id: str = "",
    task_id: str = "",
) -> list[ToolCall]:
    return tool_executor.plan(suggested_tools, connected, session_id=session_id, task_id=task_id)


def summarize_tool_plan(planned_tools: list[ToolCall]) -> str:
    if not planned_tools:
        return "当前无需工具调用"
    names = ", ".join(str(call.get("tool_name") or "").strip() for call in planned_tools)
    return f"已生成 {len(planned_tools)} 个候选工具动作：{names}"


def plan_tools_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    intent = state["intent"]
    request = state["request"]
    response_mode = str(state.get("response_mode") or short_memory.scratchpad.get("response_mode") or "").strip().lower()
    knowledge = state.get("knowledge") or short_memory.scratchpad.get("knowledge") or {}
    history_text = _format_history(state.get("conversation_history") or [])

    runtime_state.current_step = "tool_planning"
    prompt = state["build_planner_prompt"](
        request.content,
        runtime_state.route,
        knowledge_context=str(knowledge.get("context", "") or ""),
        response_mode=response_mode or "answer",
        history_text=history_text,
    )
    short_memory.scratchpad["planner_prompt"] = prompt
    short_memory.scratchpad["intent"] = intent
    short_memory.scratchpad["plan_llm_attempted"] = False
    short_memory.scratchpad["plan_source"] = "fallback"
    runtime_state.planned_tools = []
    if response_mode == "answer":
        runtime_state.trace.append(
            RouteDecision(
                stage="工具规划",
                summary="当前处于知识直答模式，无需工具调用",
                detail="response_mode=answer",
            )
        )
        return {
            "runtime_state": runtime_state,
            "short_memory": short_memory,
            "response_mode": response_mode,
        }
    try:
        short_memory.scratchpad["plan_llm_attempted"] = True
        response = state["get_llm_client"]().invoke_schema(
            prompt=prompt,
            schema_parser=parse_tool_plan_output,
            metadata={"node": "plan"},
        )
        short_memory.scratchpad["planner_result"] = response.parsed
        short_memory.scratchpad["plan_source"] = "llm"
        planned_from_llm = plan_tools(
            state["tool_executor"],
            [item["tool_name"] for item in response.parsed["tools"]],
            state["connected"],
            session_id=runtime_state.session_id,
            task_id=runtime_state.task_id,
        )
        if planned_from_llm:
            runtime_state.planned_tools = planned_from_llm
    except Exception:
        pass
    runtime_state.trace.append(
        RouteDecision(
            stage="工具规划",
            summary=summarize_tool_plan(runtime_state.planned_tools),
            detail=" -> ".join(str(call.get("tool_name") or "").strip() for call in runtime_state.planned_tools) if runtime_state.planned_tools else "暂无工具计划",
        )
    )
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "response_mode": response_mode,
    }


def _format_history(history: list[dict]) -> str:
    lines: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
