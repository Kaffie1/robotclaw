from __future__ import annotations


def build_planner_prompt(content: str, route: str) -> str:
    return (
        "你是机器人诊断规划器。"
        "请基于当前路由选择后续工具规划方向。"
        f"当前路由：{route}。"
        f"用户问题：{content}"
    )
