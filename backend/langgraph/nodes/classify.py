from __future__ import annotations

from backend.llm import parse_classify_output
from backend.runtime.models import EvidenceItem, RouteDecision


def classify_query(content: str) -> dict[str, str]:
    normalized = content.strip()
    return {
        "category": "general",
        "summary": "已完成通用问题理解",
        "detail": f"当前先按通用诊断链路处理用户请求：{normalized or '空输入'}。",
    }


def classify_query_node(state: dict) -> dict:
    request = state["request"]
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    history_text = _format_history(state.get("conversation_history") or [])

    diagnosis.evidence = [EvidenceItem(source="user", content=request.content, confidence=1.0)]
    runtime_state.current_step = "understand_query"
    intent = classify_query(request.content)
    short_memory.scratchpad["classify_llm_attempted"] = False
    short_memory.scratchpad["classify_source"] = "fallback"
    prompt = state["build_classify_prompt"](request.content, history_text=history_text)
    try:
        short_memory.scratchpad["classify_llm_attempted"] = True
        response = state["get_llm_client"]().invoke_schema(
            prompt=prompt,
            schema_parser=parse_classify_output,
            metadata={"node": "classify"},
        )
        intent = response.parsed
        short_memory.scratchpad["classify_source"] = "llm"
    except Exception:
        pass
    short_memory.scratchpad["intent"] = intent
    runtime_state.trace.append(RouteDecision(stage="问题理解", summary=intent["summary"], detail=intent["detail"]))
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "intent": intent,
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
