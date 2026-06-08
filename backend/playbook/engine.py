from __future__ import annotations

from backend.playbook.catalog import PLAYBOOKS
from backend.playbook.matcher import match_playbook


class PlaybookEngine:
    def match(self, content: str) -> dict[str, str | float]:
        return match_playbook(content)

    def analyze(self, playbook_id: str, tool_results: list[dict], connected: bool) -> dict[str, str]:
        if not connected:
            return {
                "summary": "未执行机器人检查，当前仅完成问题理解和计划生成",
                "detail": "机器人未连接，Playbook 还没有进入真实执行阶段。",
            }

        if not playbook_id:
            return {
                "summary": "走通用分析路径",
                "detail": "未命中固定 playbook，当前根据工具采集事实走通用诊断总结。",
            }

        matched = PLAYBOOKS.get(playbook_id, {})
        facts = [item.get("summary", "") for item in tool_results]
        return {
            "summary": f"Playbook 分析完成：{playbook_id}",
            "detail": f"{matched.get('analysis_hint', '已完成基础事实汇总。')} 当前事实：{'；'.join(filter(None, facts)) or '暂无'}",
        }
