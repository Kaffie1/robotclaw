from __future__ import annotations

from dataclasses import asdict

from backend.tools.permission_guard import PermissionGuard
from backend.tools.models import PlannedToolCall, ToolExecutionResult
from backend.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None, guard: PermissionGuard | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.guard = guard or PermissionGuard()

    def plan(self, category: str, connected: bool) -> list[PlannedToolCall]:
        return self.registry.plan(category, connected)

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

            results.append(self._mock_collect(tool_call))
        return results

    def to_payload(self, results: list[ToolExecutionResult]) -> list[dict]:
        return [asdict(item) for item in results]

    def _mock_collect(self, tool_call: PlannedToolCall) -> ToolExecutionResult:
        facts: dict[str, object]
        if tool_call.tool_name == "topic_monitor":
            facts = {"exists": True, "hz": 9.8, **tool_call.params}
            summary = f"{tool_call.params.get('topic', '')} 存在，频率约 9.8Hz"
        elif tool_call.tool_name == "node_status":
            facts = {"running": True, **tool_call.params}
            summary = f"节点 {tool_call.params.get('name', '')} 正在运行"
        elif tool_call.tool_name == "tf_monitor":
            facts = {"available": True, **tool_call.params}
            summary = f"TF {tool_call.params.get('from', '')}->{tool_call.params.get('to', '')} 可用"
        elif tool_call.tool_name == "config_read":
            facts = {"exists": True, **tool_call.params}
            summary = f"配置文件 {tool_call.params.get('path', '')} 可读取"
        elif tool_call.tool_name == "log_search":
            facts = {"match_count": 0, **tool_call.params}
            summary = f"日志关键字 {tool_call.params.get('keyword', '')} 未发现明显异常"
        else:
            facts = {"ok": True, **tool_call.params}
            summary = f"工具 {tool_call.tool_name} 已执行"
        return ToolExecutionResult(
            tool_name=tool_call.tool_name,
            status="completed",
            facts=facts,
            summary=summary,
        )
