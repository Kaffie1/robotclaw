from __future__ import annotations


def build_execution_mode_prompt(
    content: str,
    *,
    knowledge_context: str = "",
    history_text: str = "",
    connected: bool = False,
) -> str:
    history_block = f"最近对话上下文：\n{history_text}\n" if history_text.strip() else ""
    knowledge_block = f"已检索知识上下文：\n{knowledge_context[:1200]}\n" if knowledge_context.strip() else "当前没有检索到明确知识上下文。\n"
    return (
        "你是执行模式决策器。"
        "你的任务是判断当前用户请求更适合直接回答、进入执行/检查，还是先追问澄清。"
        "只输出一个 JSON 对象，不要输出解释，不要输出 Markdown 代码块。"
        '输出格式固定为 {"mode": "answer|act|clarify", "summary": "...", "detail": "..."}。'
        "answer 表示仅凭当前对话和知识上下文即可直接回答，不需要访问机器人运行时状态，也不需要执行工具。"
        "act 表示用户明显希望你帮他检查、执行、确认当前状态、调用接口、查看运行时信息，或必须依赖外部状态才能继续。"
        "clarify 表示当前信息不足，既不适合贸然执行，也不适合直接回答。"
        "如果用户只是询问服务名、topic 名、参数、调用方式、文档说明、流程解释，通常应选择 answer。"
        "如果用户是在让你帮他查、帮他看、帮他执行、帮他确认当前是否正常，通常应选择 act。"
        "如果当前输入是在承接上一轮对话，请结合最近对话上下文理解，不要只看当前这句话。"
        "不要因为出现“调用”“执行”等单个词就机械选择 act，要结合整句语义和上下文判断。"
        f"机器人当前连接状态：{'connected' if connected else 'disconnected'}。\n"
        f"{history_block}"
        f"{knowledge_block}"
        f"用户输入：{content}"
    )
