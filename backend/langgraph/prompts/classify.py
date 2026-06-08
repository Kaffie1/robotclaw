from __future__ import annotations


def build_classify_prompt(content: str) -> str:
    return (
        "你是机器人诊断分类器。"
        "请判断用户问题属于哪一类，并返回 JSON。"
        'category 只能是 "lidar"、"localization"、"mapping"、"general" 之一。'
        "同时给出简短 summary 和 detail。"
        f"用户问题：{content}"
    )
