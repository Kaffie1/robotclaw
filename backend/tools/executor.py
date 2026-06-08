from __future__ import annotations

from dataclasses import asdict

from backend.tools.permission_guard import PermissionGuard
from backend.tools.models import PlannedToolCall, ToolExecutionResult
from backend.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None, guard: PermissionGuard | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.guard = guard or PermissionGuard()

    def plan(self, suggested_tools: list[str], connected: bool) -> list[PlannedToolCall]:
        return self.registry.plan(suggested_tools, connected)

    def execute(self, planned_tools: list[PlannedToolCall], connected: bool) -> list[ToolExecutionResult]:
        results: list[ToolExecutionResult] = []
        for tool_call in planned_tools:
            allowed, reason = self.guard.allow(tool_call, connected)
            if not allowed:
                results.append(
                    ToolExecutionResult(
                        tool_name=tool_call.tool_name,
                        status="blocked",
                        facts={"reason": reason, "params": tool_call.params},
                        summary=reason,
                    )
                )
                continue

            results.append(self._unavailable_result(tool_call))
        return results

    def to_payload(self, results: list[ToolExecutionResult]) -> list[dict]:
        return [asdict(item) for item in results]

    def _unavailable_result(self, tool_call: PlannedToolCall) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_call.tool_name,
            status="unavailable",
            facts={
                "reason": "tool_executor_not_implemented",
                "params": tool_call.params,
            },
            summary=f"工具 {tool_call.tool_name} 尚未接入真实执行器，当前未执行。",
        )
