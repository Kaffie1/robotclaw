from __future__ import annotations


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
