from __future__ import annotations

from backend.tools.models import ToolCall


class PermissionGuard:
    def allow(self, tool_call: ToolCall, connected: bool) -> tuple[bool, str]:
        if not connected:
            return False, "机器人未连接，禁止执行远程采集工具。"
        return True, ""
