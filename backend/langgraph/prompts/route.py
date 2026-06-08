from __future__ import annotations


def build_route_prompt(content: str) -> str:
    return (
        "你是通用问题路由器。"
        "你的任务是判断当前输入更适合走模板路径，还是知识检索路径。"
        "只有在可以高置信判断某类固定流程更合适时，才倾向模板路径。"
        "如果只是知识咨询、概念解释、接口说明、状态询问、代码示例、普通聊天，优先走知识路径。"
        "不要因为局部词语相似、背景相似或场景沾边，就误判成模板路径。"
        "如果不确定，宁可走知识路径，也不要激进路由。"
        "只输出一个 JSON 对象，不要输出解释，不要输出 Markdown 代码块。"
        '输出格式固定为 {"route": "knowledge", "reason": "...", "matched_playbook_id": ""}。'
        'route 只能是 "knowledge" 或 "playbook"。'
        '如果没有明确命中的模板，matched_playbook_id 必须返回空字符串。'
        f"用户输入：{content}"
    )
