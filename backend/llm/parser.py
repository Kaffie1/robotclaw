from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, TypeVar

from backend.llm.schemas import (
    ClassifyOutput,
    ExecutionModeOutput,
    RouteOutput,
    SummaryOutput,
    ToolPlanItem,
    ToolPlanOutput,
)


T = TypeVar("T")


def extract_json_object(text: str) -> dict[str, Any]:
    normalized = _strip_think_blocks(text).strip()
    if not normalized:
        raise ValueError("LLM 返回为空，无法解析结构化输出")
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start >= 0 and end > start:
            return json.loads(normalized[start : end + 1])
        raise ValueError("LLM 返回中未找到合法 JSON 对象")


def to_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError("仅支持 dataclass 或 dict 结构化结果")


def parse_route_output(payload: dict[str, Any]) -> RouteOutput:
    return RouteOutput(
        route=str(payload.get("route", "")).strip() or "knowledge",
        reason=str(payload.get("reason", "")).strip(),
        matched_playbook_id=str(payload.get("matched_playbook_id", "")).strip(),
    )


def parse_classify_output(payload: dict[str, Any]) -> ClassifyOutput:
    category = str(payload.get("category", "")).strip() or "general"
    return ClassifyOutput(
        category=category,
        summary=str(payload.get("summary", "")).strip() or "已完成通用问题理解",
        detail=str(payload.get("detail", "")).strip() or "当前先走通用聊天诊断链路。",
    )


def parse_execution_mode_output(payload: dict[str, Any]) -> ExecutionModeOutput:
    mode = str(payload.get("mode", "")).strip().lower() or "answer"
    if mode not in {"answer", "act", "clarify"}:
        mode = "answer"
    return ExecutionModeOutput(
        mode=mode,
        summary=str(payload.get("summary", "")).strip() or "已完成执行意图判断",
        detail=str(payload.get("detail", "")).strip() or f"当前按 {mode} 模式处理。",
    )


def parse_tool_plan_output(payload: dict[str, Any]) -> ToolPlanOutput:
    raw_tools = payload.get("tools") or []
    tools = [
        ToolPlanItem(
            tool_name=str(item.get("tool_name", "")).strip(),
            reason=str(item.get("reason", "")).strip(),
        )
        for item in raw_tools
        if isinstance(item, dict) and str(item.get("tool_name", "")).strip()
    ]
    return ToolPlanOutput(
        category=str(payload.get("category", "")).strip() or "general",
        tools=tools,
        summary=str(payload.get("summary", "")).strip(),
    )


def parse_summary_output(payload: dict[str, Any]) -> SummaryOutput:
    evidence = [str(item).strip() for item in (payload.get("evidence") or []) if str(item).strip()]
    next_steps = [str(item).strip() for item in (payload.get("next_steps") or []) if str(item).strip()]
    return SummaryOutput(
        summary=str(payload.get("summary", "")).strip(),
        evidence=evidence,
        next_steps=next_steps,
    )


def _strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
