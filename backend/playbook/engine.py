from __future__ import annotations

from backend.playbook.catalog import PLAYBOOKS
from backend.playbook.matcher import match_playbook


class PlaybookEngine:
    def match(self, content: str) -> dict[str, str | float]:
        return match_playbook(content)

    def analyze(
        self,
        playbook_id: str,
        tool_results: list[dict],
        connected: bool,
        planned_tool_count: int = 0,
    ) -> dict[str, str]:
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

        if not playbook_id:
            return {
                "summary": "走通用分析路径",
                "detail": "当前未使用固定模板，系统根据已采集的事实生成通用分析结果。",
            }

        matched = PLAYBOOKS.get(playbook_id, {})
        facts = [item.get("summary", "") for item in tool_results]
        return {
            "summary": f"模板分析完成：{playbook_id}",
            "detail": f"{matched.get('analysis_hint', '已完成基础事实汇总。')} 当前事实：{'；'.join(filter(None, facts)) or '暂无'}",
        }
