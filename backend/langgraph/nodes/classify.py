from __future__ import annotations

from backend.llm import parse_classify_output
from backend.runtime.models import EvidenceItem, RouteDecision


def classify_query(content: str) -> dict[str, str]:
    normalized = content.strip()
    if any(keyword in normalized for keyword in ("雷达", "lidar", "/scan")):
        return {
            "category": "lidar",
            "summary": "识别为传感器/雷达异常问题",
            "detail": "用户问题包含雷达或扫描数据关键词，优先按传感器链路处理。",
        }
    if any(keyword in normalized for keyword in ("定位", "漂移", "localization", "amcl")):
        return {
            "category": "localization",
            "summary": "识别为定位异常问题",
            "detail": "问题与定位缺失、漂移或定位质量下降相关。",
        }
    if any(keyword in normalized for keyword in ("地图", "map", "加载失败")):
        return {
            "category": "mapping",
            "summary": "识别为地图/建图相关问题",
            "detail": "问题包含地图加载或地图服务相关描述。",
        }
    return {
        "category": "general",
        "summary": "识别为通用运维问答",
        "detail": "当前先走通用聊天诊断链路，后续可继续细分到更多故障类型。",
    }


def classify_query_node(state: dict) -> dict:
    request = state["request"]
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]

    diagnosis.evidence = [EvidenceItem(source="user", content=request.content, confidence=1.0)]
    runtime_state.current_step = "understand_query"
    intent = classify_query(request.content)
    prompt = state["build_classify_prompt"](request.content)
    try:
        response = state["llm_client"].invoke_schema(
            prompt=prompt,
            schema_parser=parse_classify_output,
            metadata={"node": "classify"},
        )
        intent = response.parsed
    except Exception:
        pass
    runtime_state.trace.append(RouteDecision(stage="问题理解", summary=intent["summary"], detail=intent["detail"]))
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "intent": intent,
    }
