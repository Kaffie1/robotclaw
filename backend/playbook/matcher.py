from __future__ import annotations


def match_playbook(content: str) -> dict[str, str | float]:
    normalized = content.strip().lower()
    if any(keyword in normalized for keyword in ("雷达", "lidar", "/scan")):
        return {
            "id": "lidar-no-data",
            "topic": "perception",
            "summary": "命中 playbook：lidar-no-data",
            "detail": "优先走固化经验，检查 /scan topic、驱动进程和日志异常。",
            "confidence": 0.92,
        }
    if any(keyword in normalized for keyword in ("定位", "漂移", "amcl", "无法导航")):
        return {
            "id": "no-localization",
            "topic": "location",
            "summary": "命中 playbook：no-localization",
            "detail": "优先走定位故障 playbook，检查定位节点、TF 链路和地图状态。",
            "confidence": 0.88,
        }
    if any(keyword in normalized for keyword in ("地图", "map", "加载失败")):
        return {
            "id": "map-server-failure",
            "topic": "map_server",
            "summary": "命中 playbook：map-server-failure",
            "detail": "优先走地图服务故障 playbook，检查进程、文件和启动参数。",
            "confidence": 0.84,
        }
    return {
        "id": "",
        "topic": "general",
        "summary": "未命中固定 playbook，进入知识库兜底路径",
        "detail": "当前继续走知识检索 + 工具规划路径。",
        "confidence": 0.35,
    }
