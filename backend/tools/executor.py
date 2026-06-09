from __future__ import annotations

from backend.ssh import SSHManager
from backend.tools.permission_guard import PermissionGuard
from backend.tools.models import ToolCall, ToolResult, build_tool_result, schema_to_payload
from backend.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        guard: PermissionGuard | None = None,
        ssh_manager: SSHManager | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.guard = guard or PermissionGuard()
        self.ssh_manager = ssh_manager

    def plan(
        self,
        suggested_tools: list[str],
        connected: bool,
        *,
        session_id: str = "",
        task_id: str = "",
    ) -> list[ToolCall]:
        return self.registry.plan(suggested_tools, connected, session_id=session_id, task_id=task_id)

    def execute(self, planned_tools: list[ToolCall], connected: bool) -> list[ToolResult]:
        results: list[ToolResult] = []
        for tool_call in planned_tools:
            allowed, reason = self.guard.allow(tool_call, connected)
            tool = self.registry.get_tool(str(tool_call.get("tool_name") or "").strip())
            if not allowed:
                results.append(
                    build_tool_result(
                        call_id=str(tool_call.get("call_id") or "").strip(),
                        tool_name=str(tool_call.get("tool_name") or "").strip(),
                        success=False,
                        status="blocked",
                        facts={"reason": reason, "params": dict(tool_call.get("params") or {})},
                        summary=reason,
                        error=reason,
                        data={
                            "params": dict(tool_call.get("params") or {}),
                            "output_schema": schema_to_payload(tool.output_schema) if tool else {},
                            "result_schema": dict(tool.result_schema) if tool else {},
                        },
                    )
                )
                continue

            if tool is None or tool.execute is None:
                results.append(self._unavailable_result(tool_call, tool=tool))
                continue

            params = dict(tool_call.get("params") or {})
            params["_call_id"] = str(tool_call.get("call_id") or "").strip()
            params["_session_id"] = str(tool_call.get("session_id") or "").strip()
            params["_task_id"] = str(tool_call.get("task_id") or "").strip()
            params["_ssh_manager"] = self.ssh_manager
            params["_tool"] = tool
            result = dict(tool.execute(params))
            result.setdefault("call_id", params["_call_id"])
            result.setdefault("tool_name", tool.name)
            results.append(result)
        return results

    def to_payload(self, results: list[ToolResult]) -> list[dict]:
        return [dict(item) for item in results]

    def _unavailable_result(self, tool_call: ToolCall, *, tool=None) -> ToolResult:
        return build_tool_result(
            call_id=str(tool_call.get("call_id") or "").strip(),
            tool_name=str(tool_call.get("tool_name") or "").strip(),
            success=False,
            status="unavailable",
            facts={
                "reason": "tool_executor_not_implemented",
                "params": dict(tool_call.get("params") or {}),
            },
            summary=f"工具 {tool_call.get('tool_name', '')} 尚未接入真实执行器，当前未执行。",
            error="tool_executor_not_implemented",
            data={
                "params": dict(tool_call.get("params") or {}),
                "input_schema": schema_to_payload(tool.input_schema) if tool else {},
                "output_schema": schema_to_payload(tool.output_schema) if tool else {},
                "result_schema": dict(tool.result_schema) if tool else {},
            },
            raw_output="",
        )
