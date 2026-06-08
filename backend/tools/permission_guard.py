from __future__ import annotations

from backend.tools.models import PlannedToolCall


class PermissionGuard:
    def allow(self, tool_call: PlannedToolCall, connected: bool) -> tuple[bool, str]:
        if tool_call.tool_name == "connect_robot":
            return False, "当前需要先由用户在连接面板建立机器人连接。"
        if not connected:
            return False, "机器人未连接，禁止执行远程采集工具。"
        return True, ""
