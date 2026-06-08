from __future__ import annotations

from backend.tools.models import PlannedToolCall


class ToolRegistry:
    def plan(self, category: str, connected: bool) -> list[PlannedToolCall]:
        if not connected:
            return [
                PlannedToolCall(
                    tool_name="connect_robot",
                    params={"required": True, "reason": "执行机器人诊断前需要建立连接"},
                )
            ]

        plans: dict[str, list[PlannedToolCall]] = {
            "lidar": [
                PlannedToolCall(tool_name="topic_monitor", params={"topic": "/scan"}),
                PlannedToolCall(tool_name="node_status", params={"name": "lidar_driver"}),
                PlannedToolCall(tool_name="log_search", params={"keyword": "ERROR"}),
            ],
            "localization": [
                PlannedToolCall(tool_name="node_status", params={"name": "amcl"}),
                PlannedToolCall(tool_name="tf_monitor", params={"from": "map", "to": "base_link"}),
                PlannedToolCall(tool_name="topic_monitor", params={"topic": "/amcl_pose"}),
            ],
            "mapping": [
                PlannedToolCall(tool_name="node_status", params={"name": "map_server"}),
                PlannedToolCall(tool_name="config_read", params={"path": "/maps/current.yaml"}),
                PlannedToolCall(tool_name="log_search", params={"keyword": "map"}),
            ],
        }
        return plans.get(
            category,
            [
                PlannedToolCall(tool_name="shell_command", params={"command": "echo health-check"}),
                PlannedToolCall(tool_name="log_search", params={"keyword": "ERROR"}),
            ],
        )
