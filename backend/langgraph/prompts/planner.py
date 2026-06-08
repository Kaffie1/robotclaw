from __future__ import annotations


def build_planner_prompt(
    content: str,
    route: str,
    *,
    knowledge_context: str = "",
    response_mode: str = "",
    history_text: str = "",
) -> str:
    knowledge_block = f"已检索知识上下文：{knowledge_context[:800]}。" if knowledge_context.strip() else "当前没有可用知识上下文。"
    response_mode_hint = f"当前回答模式：{response_mode or 'unknown'}。" if response_mode else ""
    history_block = f"最近对话上下文：\n{history_text}\n" if history_text.strip() else ""
    return (
        "你是通用工具规划器。"
        "你的任务是判断当前请求是否真的需要外部工具。"
        "如果当前输入是在追问上一轮内容，请结合最近对话一起判断，不要把上下文断开。"
        "如果仅凭现有信息就可以直接回答，请返回空 tools。"
        "只有在必须依赖外部状态、远程环境、运行时信息或文件内容时，才规划工具。"
        "不要为了显得完整而强行规划工具，不要编造工具名。"
        "只输出一个 JSON 对象，不要输出解释，不要输出 Markdown 代码块。"
        '输出格式固定为 {"category": "...", "tools": [{"tool_name": "...", "reason": "..."}], "summary": "..."}。'
        "tools 可以为空数组。"
        "tool_name 只能填写后端可能识别的真实工具名，不能写自然语言描述。"
        "summary 用一句短话概括为什么需要工具，或为什么不需要工具。"
        f"当前路由：{route}。"
        f"{response_mode_hint}"
        f"{history_block}"
        f"{knowledge_block}"
        f"用户输入：{content}"
    )
