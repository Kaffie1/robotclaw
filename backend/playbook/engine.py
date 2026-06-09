from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backend.playbook.executor import execute_playbook
from backend.playbook.loader import find_playbook_by_id
from backend.playbook.matcher import match_playbook
from backend.playbook.models import BTNodeSpec
from backend.rule import RuleEngine, RuleRegistry
from backend.tools.models import ToolCall, build_tool_call


class PlaybookEngine:
    def __init__(self) -> None:
        self.rule_registry = RuleRegistry()
        self.rule_engine = RuleEngine(self.rule_registry)

    def match(self, content: str) -> dict[str, str | float]:
        return match_playbook(content)

    def execute(
        self,
        playbook_id: str,
        *,
        tool_executor,
        connected: bool,
        context: dict[str, Any] | None = None,
        resume: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = find_playbook_by_id(playbook_id)
        if spec is None:
            return {
                "playbook_id": playbook_id,
                "executed": False,
                "passed": False,
                "reason": "playbook_not_found",
                "steps": [],
            }
        missing_tools = sorted(_collect_missing_tools(spec.root, tool_executor=tool_executor))
        if missing_tools:
            missing_text = "、".join(missing_tools)
            return {
                "playbook_id": spec.meta.playbook_id,
                "playbook_title": spec.meta.name,
                "executed": False,
                "passed": False,
                "reason": "missing_tools",
                "missing_tools": missing_tools,
                "steps": [],
                "conclusion": f"{spec.meta.name} 暂时无法自动执行",
                "next_action": (
                    "当前系统暂时还不能自动完成这一步，"
                    "需要由维护人员补充相应能力后才能继续处理。"
                ),
                "developer_detail": f"playbook {spec.meta.name} 缺少可执行工具：{missing_text}",
                "current_node_id": spec.root.node_id,
                "completed_nodes": [],
                "failed_nodes": [spec.root.node_id],
                "playbook_context": dict(context or {}),
                "rule_results": [],
                "pending_confirmation": None,
            }
        self.rule_registry = RuleRegistry()
        self.rule_registry.load_from_file(str(getattr(spec.meta, "rules_source_path", "")))
        self.rule_engine = RuleEngine(self.rule_registry)
        return execute_playbook(
            spec,
            tool_executor=tool_executor,
            rule_engine=self.rule_engine,
            connected=connected,
            context=context or {},
            resume=resume or {},
        )

    def analyze(
        self,
        playbook_id: str,
        tool_results: list[dict],
        connected: bool,
        planned_tool_count: int = 0,
        execution: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        if execution:
            conclusion = str(execution.get("conclusion") or "").strip()
            next_action = str(execution.get("next_action") or "").strip()
            if conclusion or next_action:
                return {
                    "summary": conclusion or f"playbook {playbook_id} 执行完成",
                    "detail": next_action or f"共执行 {len(execution.get('steps') or [])} 个节点。",
                }

        if planned_tool_count <= 0:
            return {
                "summary": "当前可以直接给出结论。",
                "detail": "本次请求不依赖外部工具或连接条件，可以直接根据现有信息回复。",
            }
        if not connected:
            return {
                "summary": "未执行外部工具，当前仅完成问题理解和计划生成",
                "detail": "当前缺少外部连接条件，因此还没有进入工具执行阶段。",
            }
        facts = [item.get("summary", "") for item in tool_results if isinstance(item, dict)]
        return {
            "summary": f"模板分析完成：{playbook_id or '通用路径'}",
            "detail": f"当前事实：{'；'.join(filter(None, facts)) or '暂无'}",
        }

    def build_action_plan(self, execution: dict[str, Any]) -> list[ToolCall]:
        plans: list[ToolCall] = []
        for step in execution.get("steps") or []:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or "").strip()
            if not tool_name:
                continue
            plans.append(build_tool_call(tool_name, params=dict(step.get("arguments") or {})))
        return plans


def _collect_missing_tools(node: BTNodeSpec, *, tool_executor) -> set[str]:
    missing: set[str] = set()
    registry = getattr(tool_executor, "registry", None)
    tool_name = str(getattr(node, "tool", "") or "").strip()
    if tool_name and (registry is None or registry.get_tool(tool_name) is None):
        missing.add(tool_name)
    for child in node.children:
        missing.update(_collect_missing_tools(child, tool_executor=tool_executor))
    return missing
