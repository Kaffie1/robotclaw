from __future__ import annotations

from backend.tools.models import Tool, ToolCall, build_tool_call, tool_to_definition
from backend.tools.specs import (
    build_ping_host_tool,
    build_remote_execute_tool,
    build_ros_service_call_tool,
    build_ros_topic_echo_tool,
    build_topic_monitor_tool,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = self._build_tools()

    def list_definitions(self) -> list[dict]:
        return [tool_to_definition(tool) for tool in self._tools.values()]

    def get_tool(self, tool_name: str) -> Tool | None:
        return self._tools.get(str(tool_name or "").strip())

    def plan(
        self,
        suggested_tools: list[str],
        connected: bool,
        *,
        session_id: str = "",
        task_id: str = "",
    ) -> list[ToolCall]:
        normalized_tools: list[str] = []
        for tool_name in suggested_tools:
            normalized = str(tool_name).strip()
            if normalized and normalized in self._tools and normalized not in normalized_tools:
                normalized_tools.append(normalized)

        if not normalized_tools:
            return []

        if not connected:
            return []
        return [
            build_tool_call(
                tool_name,
                session_id=session_id,
                task_id=task_id,
            )
            for tool_name in normalized_tools
        ]

    def _build_tools(self) -> dict[str, Tool]:
        tools = [
            build_ping_host_tool(),
            build_remote_execute_tool(),
            build_ros_service_call_tool(),
            build_ros_topic_echo_tool(),
            build_topic_monitor_tool(),
        ]
        return {tool.name: tool for tool in tools}
