from __future__ import annotations


def build_classify_prompt(content: str, *, history_text: str = "") -> str:
    history_block = f"最近对话上下文：\n{history_text}\n" if history_text.strip() else ""
    return (
        "你是通用输入分类器。"
        "你的任务是判断这条用户输入更像普通对话、知识问答，还是需要进一步分析或处理的问题。"
        "如果当前输入明显是在承接上一轮对话，请结合最近对话上下文理解，不要把脱离上下文后的短句误判。"
        "只输出一个 JSON 对象，不要输出解释，不要输出 Markdown 代码块。"
        '输出格式固定为 {"category": "...", "summary": "...", "detail": "..."}。'
        'category 使用简洁稳定的字符串；如果只是问候、寒暄、确认在线、普通闲聊，可返回 "chat"。'
        "如果输入包含明确的咨询、分析、排查、处理、执行、恢复、配置、状态确认等意图，请返回更合适的通用分类。"
        "不要假设具体硬件、业务域、节点名、topic 名或故障类型。"
        "如果无法特别明确地区分，就保守返回通用分类，而不是编造细粒度类别。"
        "summary 用一句短话概括分类结果。"
        "detail 用一句短话解释为什么这样分类，但不要展开排查步骤。"
        f"{history_block}"
        f"用户输入：{content}"
    )
