from __future__ import annotations


def build_summary_prompt(content: str) -> str:
    return (
        "你是机器人诊断总结器。"
        "请根据当前证据与分析结论生成面向用户的最终摘要。"
        f"用户问题：{content}"
    )
