from __future__ import annotations


def build_route_prompt(content: str) -> str:
    return (
        "你是机器人诊断路由器。"
        "请先判断用户问题更像 playbook 路径还是知识检索路径。"
        f"用户问题：{content}"
    )
