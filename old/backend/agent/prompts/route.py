def build_fault_route_prompt(user_message: str, playbooks: list[dict[str, str]]) -> str:
    title_lines = "\n".join(
        _render_candidate_line(item)
        for item in playbooks
        if item.get("id") and item.get("title")
    )
    return (
        "你是机器人 workflow 路由器。"
        "请根据用户问题，从候选 workflow title 中选择语义上足够接近、且明确描述的是同一类目标或处理流程的一个。"
        "候选 workflow 同时可能包含 fault 和 normal 两类。"
        "只有在用户问题和某个 workflow title 语义足够像、能够高置信判断为同一类流程时，才允许返回该 workflow。"
        "对于 normal workflow，除了看目标动作本身，还要结合它的入口输入要求判断用户是否真的在请求该流程。"
        "不要因为局部词语相关、背景场景相关、依赖关系相关，就盲目匹配到某个 workflow。"
        "如果只是知识咨询、接口查询、状态查看、代码示例、参数说明，或者你不能高置信确认应进入某个既有 workflow，就返回空字符串。"
        "宁可不匹配，也不要误匹配。"
        "只输出一个 JSON 对象，不要输出解释。\n"
        '输出格式: {"playbook_id": "", "reason": ""}\n'
        f"用户问题: {user_message}\n"
        f"候选 workflows:\n{title_lines}"
    )


def _render_candidate_line(item: dict[str, str]) -> str:
    playbook_id = item.get("id", "")
    workflow_type = item.get("type", "")
    title = item.get("title", "")
    requirements = item.get("input_requirements") if isinstance(item.get("input_requirements"), list) else []
    examples = item.get("entry_examples") if isinstance(item.get("entry_examples"), list) else []
    line = f"- {playbook_id} [{workflow_type}]: {title}"
    if requirements:
        line += f"\n  入口要求: {'；'.join(str(req).strip() for req in requirements if str(req).strip())}"
    if examples:
        line += f"\n  示例问法: {'；'.join(str(example).strip() for example in examples if str(example).strip())}"
    return line
