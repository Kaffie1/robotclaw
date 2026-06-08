from __future__ import annotations


class KnowledgeService:
    def retrieve(self, topic: str) -> dict[str, str | float]:
        knowledge_map = {
            "perception": ("感知知识", "优先检索雷达驱动、/scan 数据频率和日志关键字。", 0.83),
            "location": ("定位知识", "优先检索定位节点、TF 和地图定位常见故障经验。", 0.8),
            "map_server": ("地图知识", "优先检索地图文件路径、map_server 启动方式与加载错误。", 0.78),
            "general": ("通用知识", "暂时保留通用运维知识入口，等待后续接入真实 RAG。", 0.45),
        }
        label, detail, confidence = knowledge_map.get(topic, knowledge_map["general"])
        return {
            "summary": f"选择知识域：{label}",
            "detail": detail,
            "confidence": confidence,
        }
