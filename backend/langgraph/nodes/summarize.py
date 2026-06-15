from __future__ import annotations

from backend.langgraph.prompts import build_smalltalk_prompt, build_summary_request_prompt
from backend.llm import parse_summary_output
from backend.runtime.models import RouteDecision, SolutionItem


def build_solutions(
    *,
    connected: bool,
    robot_ref: str,
    host: str,
    analysis: dict[str, str],
    planned_tool_count: int,
) -> list[SolutionItem]:
    if planned_tool_count <= 0:
        return []

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
            title="进入执行阶段",
            detail=f"当前已连接 {robot_ref}（{host}），已完成第一批工具执行，可继续深化分析。",
        ),
        SolutionItem(
            title="保留自动修复入口",
            detail=f"当前分析结论：{analysis['summary']}。后续可在 PermissionGuard 后挂接自动修复动作。",
        ),
    ]


def compose_answer(
    *,
    analysis: dict[str, str],
    solutions: list[SolutionItem],
    connected: bool,
    planned_tool_count: int,
) -> str:
    lines = [analysis.get("summary", "").strip() or "当前已形成阶段性结论。"]
    detail = str(analysis.get("detail", "") or "").strip()
    if _should_include_user_detail(detail):
        lines.append(detail)
    elif planned_tool_count > 0 and not connected:
        lines.append("当前需要先满足外部连接条件后再继续执行。")
    elif solutions:
        suggestion = _pick_user_visible_solution(solutions)
        if suggestion:
            lines.append(suggestion)
    return "\n".join(lines)


def summarize_response_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    envelope = state["envelope"]
    request = state["request"]
    intent = state.get("intent") or short_memory.scratchpad.get("intent") or {}
    knowledge = state.get("knowledge") or short_memory.scratchpad.get("knowledge") or {}
    history_text = _format_history(state.get("conversation_history") or [])
    analysis = state.get("analysis") or short_memory.scratchpad.get("analysis") or {
        "summary": "当前已完成阶段性诊断",
        "detail": "本次流程已形成阶段性结果，可根据当前状态继续下一步。",
    }
    if knowledge.get("context") and not state.get("analysis") and not short_memory.scratchpad.get("analysis"):
        analysis = {
            "summary": str(knowledge.get("summary") or "已检索到相关知识片段"),
            "detail": str(knowledge.get("detail") or knowledge.get("context") or "").strip(),
        }

    diagnosis.solutions = build_solutions(
        connected=state["connected"],
        robot_ref=envelope.robot_config.robot_ref,
        host=envelope.robot_config.host,
        analysis=analysis,
        planned_tool_count=len(runtime_state.planned_tools),
    )
    waiting_mode = runtime_state.current_step in {"waiting_confirm", "waiting_input"}
    seed_answer = str(diagnosis.final_answer or "").strip()
    if not seed_answer and waiting_mode:
        confirmation = short_memory.pending_confirmation or {}
        seed_answer = str(confirmation.get("message") or analysis.get("summary") or "").strip()
    if not seed_answer:
        seed_answer = compose_answer(
            analysis=analysis,
            solutions=diagnosis.solutions,
            connected=state["connected"],
            planned_tool_count=len(runtime_state.planned_tools),
        )

    if not waiting_mode:
        runtime_state.current_step = "solution_generation"
    prompt = state["build_summary_prompt"](
        request.content,
        knowledge_context=str(knowledge.get("context", "") or ""),
        citations_text=_format_citations(knowledge.get("citations") or []),
        history_text=history_text,
    )
    short_memory.scratchpad["summary_prompt"] = prompt
    short_memory.scratchpad["summary_llm_attempted"] = False
    short_memory.scratchpad["summary_source"] = "fallback"
    runtime_state.trace.append(
        RouteDecision(
            stage="解决方案生成",
            summary="已生成面向用户的处理建议",
            detail="根据当前证据和分析结果输出下一步建议。",
        )
    )
    if _should_use_smalltalk(intent=intent, knowledge=knowledge, request_content=request.content):
        diagnosis.final_answer = _smalltalk_answer(state["get_llm_client"], request.content)
        short_memory.scratchpad["summary_source"] = "llm"
        if not waiting_mode:
            runtime_state.current_step = "completed"
            runtime_state.finished = True
        return {
            "runtime_state": runtime_state,
            "diagnosis": diagnosis,
            "short_memory": short_memory,
        }
    diagnosis.final_answer = seed_answer
    try:
        short_memory.scratchpad["summary_llm_attempted"] = True
        response = state["get_llm_client"]().invoke_schema(
            prompt=build_summary_request_prompt(
                prompt=prompt,
                query=request.content,
                trace=runtime_state.trace,
                analysis=analysis,
                solutions=diagnosis.solutions,
                knowledge_context=str(knowledge.get("context", "") or "").strip(),
                citations_text=_format_citations(knowledge.get("citations") or []),
                seed_answer=seed_answer,
            ),
            schema_parser=parse_summary_output,
            metadata={"node": "summarize"},
        )
        short_memory.scratchpad["summary_result"] = response.parsed
        if response.parsed["summary"] and _is_summary_consistent(seed_answer=seed_answer, candidate=response.parsed["summary"]):
            diagnosis.final_answer = response.parsed["summary"]
            short_memory.scratchpad["summary_source"] = "llm"
        elif response.parsed["summary"]:
            short_memory.scratchpad["summary_source"] = "guarded_fallback"
    except Exception:
        pass
    if not waiting_mode:
        runtime_state.current_step = "completed"
        runtime_state.finished = True
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
    }


_NEGATIVE_MARKERS = (
    "失败",
    "异常",
    "错误",
    "超时",
    "未恢复",
    "没有",
    "无",
    "无法",
    "不通",
    "未找到",
    "中断",
    "挂起",
    "等待",
)

_POSITIVE_MARKERS = (
    "成功",
    "正常",
    "恢复",
    "已恢复",
    "已完成",
    "可用",
    "已连接",
    "正常输出",
)

_POSITIVE_PHRASES = (
    "未发现异常",
    "连接正常",
    "通道正常",
    "状态正常",
    "运行正常",
)

_NEGATIVE_PHRASES = (
    "无法确认",
    "连接异常",
    "检查失败",
    "未能恢复",
    "没有数据",
)

_NEUTRAL_PHRASES = (
    "是否正常",
    "是否有数据",
    "能否确认",
)


def _detect_conclusion_polarity(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return "unknown"
    positive_hits = sum(1 for phrase in _POSITIVE_PHRASES if phrase in normalized)
    negative_hits = sum(1 for phrase in _NEGATIVE_PHRASES if phrase in normalized)
    scrubbed = normalized
    for phrase in _POSITIVE_PHRASES + _NEGATIVE_PHRASES + _NEUTRAL_PHRASES:
        scrubbed = scrubbed.replace(phrase, " ")
    has_negative = negative_hits > 0 or any(marker in scrubbed for marker in _NEGATIVE_MARKERS)
    has_positive = positive_hits > 0 or any(marker in scrubbed for marker in _POSITIVE_MARKERS)
    if has_negative and not has_positive:
        return "negative"
    if has_positive and not has_negative:
        return "positive"
    return "unknown"


def _is_summary_consistent(*, seed_answer: str, candidate: str) -> bool:
    seed_polarity = _detect_conclusion_polarity(seed_answer)
    candidate_polarity = _detect_conclusion_polarity(candidate)
    if seed_polarity == "unknown" or candidate_polarity == "unknown":
        return True
    return seed_polarity == candidate_polarity


def _is_smalltalk_intent(intent: dict) -> bool:
    return str(intent.get("category", "")).strip().lower() in {"chat", "greeting", "smalltalk"}


def _should_use_smalltalk(*, intent: dict, knowledge: dict, request_content: str) -> bool:
    if not _is_smalltalk_intent(intent):
        return False
    if str(knowledge.get("context", "") or "").strip():
        return False
    normalized = str(request_content or "").strip().lower()
    technical_markers = {"python", "代码", "接口", "topic", "建图", "mapping", "slam", "ros"}
    return not any(marker in normalized for marker in technical_markers)


def _smalltalk_answer(get_llm_client, content: str) -> str:
    fallback = "你好，我是 RobotClaw 诊断助手，可以帮你分析问题、查看状态并给出处理建议。"
    try:
        response = get_llm_client().invoke_text(
            prompt=build_smalltalk_prompt(content),
            metadata={"node": "smalltalk"},
        )
        text = response.content.strip()
        return text or fallback
    except Exception:
        return fallback


def _format_citations(citations: list[dict]) -> str:
    lines: list[str] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename", "") or "").strip()
        chunk_id = str(item.get("chunk_id", "") or "").strip()
        if filename or chunk_id:
            lines.append(f"- {filename}#{chunk_id}")
    return "\n".join(lines)


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


_PROCESS_DETAIL_MARKERS = (
    "重复调用",
    "重复检查",
    "系统已阻止",
    "收口总结",
    "工具调用",
    "内部",
    "节点",
    "轨迹",
    "流程",
    "本轮不再重复执行同一检查",
)


def _should_include_user_detail(detail: str) -> bool:
    normalized = str(detail or "").strip()
    if not normalized:
        return False
    return not any(marker in normalized for marker in _PROCESS_DETAIL_MARKERS)


def _pick_user_visible_solution(solutions: list[SolutionItem]) -> str:
    for solution in solutions:
        detail = str(solution.detail or "").strip()
        if detail:
            return detail
    return ""
