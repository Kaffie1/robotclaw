from __future__ import annotations

from backend.tools.models import PlannedToolCall


class ToolRegistry:
    SUPPORTED_TOOLS: tuple[str, ...] = (
        "topic_monitor",
        "node_status",
        "tf_monitor",
        "config_read",
        "log_search",
        "shell_command",
    )

    def list_definitions(self) -> list[dict[str, str]]:
        return [
            {
                "name": tool_name,
                "module": "runtime_tools",
            }
            for tool_name in self.SUPPORTED_TOOLS
        ]

    def plan(self, suggested_tools: list[str], connected: bool) -> list[PlannedToolCall]:
        normalized_tools: list[str] = []
        for tool_name in suggested_tools:
            normalized = str(tool_name).strip()
            if normalized and normalized in self.SUPPORTED_TOOLS and normalized not in normalized_tools:
                normalized_tools.append(normalized)

        if not normalized_tools:
            return []

        if not connected:
            return [
                PlannedToolCall(
                    tool_name="connect_robot",
                    params={"required": True, "reason": "执行机器人诊断前需要建立连接"},
                )
            ]
        return [PlannedToolCall(tool_name=tool_name) for tool_name in normalized_tools]
