from __future__ import annotations

from backend.llm import parse_summary_output
from backend.runtime.models import RouteDecision, SolutionItem


def build_solutions(
    *,
    connected: bool,
    robot_ref: str,
    host: str,
    analysis: dict[str, str],
) -> list[SolutionItem]:
    if not connected:
        return [
            SolutionItem(
                title="先连接机器人",
                detail="当前已完成问题理解、知识选择和工具规划，但机器人未连接，无法继续采集事实。",
            ),
            SolutionItem(
                title="连接后继续执行",
                detail="连接目标机器人后，可以继续执行 ToolExecutor 并进入真实诊断阶段。",
            ),
        ]

    return [
        SolutionItem(
            title="进入诊断执行阶段",
            detail=f"当前已连接 {robot_ref}（{host}），已完成第一批机器人检查，可继续深化分析。",
        ),
        SolutionItem(
            title="保留自动修复入口",
            detail=f"当前分析结论：{analysis['summary']}。后续可在 PermissionGuard 后挂接自动修复动作。",
        ),
    ]


def compose_answer(
    *,
    query: str,
    trace: list[RouteDecision],
    solutions: list[SolutionItem],
    connected: bool,
    robot_ref: str,
    host: str,
) -> str:
    lines = [f"已收到你的问题：“{query}”。", "", "当前链路按设计完成了以下阶段："]
    for item in trace:
        lines.append(f"- {item.stage}：{item.summary}")
    lines.append("")
    if connected and robot_ref:
        lines.append(f"当前机器人已连接：{robot_ref}（{host}）。")
    else:
        lines.append("当前还没有连接机器人，所以链路停在可执行前的规划/阻塞状态。")
    lines.append("")
    lines.append("建议下一步：")
    for solution in solutions:
        lines.append(f"- {solution.detail}")
    return "\n".join(lines)


def summarize_response_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    envelope = state["envelope"]
    request = state["request"]
    analysis = state["analysis"]

    runtime_state.current_step = "solution_generation"
    prompt = state["build_summary_prompt"](request.content)
    short_memory.scratchpad["summary_prompt"] = prompt
    diagnosis.solutions = build_solutions(
        connected=state["connected"],
        robot_ref=envelope.robot_config.robot_ref,
        host=envelope.robot_config.host,
        analysis=analysis,
    )
    runtime_state.trace.append(
        RouteDecision(
            stage="解决方案生成",
            summary="已生成面向用户的处理建议",
            detail="根据当前证据和分析结果输出下一步建议。",
        )
    )
    diagnosis.final_answer = compose_answer(
        query=request.content,
        trace=runtime_state.trace,
        solutions=diagnosis.solutions,
        connected=state["connected"],
        robot_ref=envelope.robot_config.robot_ref,
        host=envelope.robot_config.host,
    )
    try:
        response = state["llm_client"].invoke_schema(
            prompt=_build_summary_request(
                prompt=prompt,
                query=request.content,
                trace=runtime_state.trace,
                analysis=analysis,
                solutions=diagnosis.solutions,
            ),
            schema_parser=parse_summary_output,
            metadata={"node": "summarize"},
        )
        short_memory.scratchpad["summary_result"] = response.parsed
        if response.parsed["summary"]:
            diagnosis.final_answer = response.parsed["summary"]
    except Exception:
        pass
    runtime_state.current_step = "completed"
    runtime_state.finished = True
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
    }


def _build_summary_request(
    *,
    prompt: str,
    query: str,
    trace: list[RouteDecision],
    analysis: dict[str, str],
    solutions: list[SolutionItem],
) -> str:
    trace_text = "\n".join(f"- {item.stage}: {item.summary}" for item in trace)
    solution_text = "\n".join(f"- {item.detail}" for item in solutions)
    return (
        f"{prompt}\n"
        "请返回 JSON，字段包含 summary、evidence、next_steps。\n"
        f"用户问题：{query}\n"
        f"诊断轨迹：\n{trace_text}\n"
        f"分析结论：{analysis.get('summary', '')}\n"
        f"建议：\n{solution_text}"
    )
