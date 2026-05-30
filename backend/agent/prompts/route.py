def build_fault_route_prompt(user_message: str, playbooks: list[dict[str, str]]) -> str:
    title_lines = "\n".join(
        f"- {item['id']}: {item['title']}"
        for item in playbooks
        if item.get("id") and item.get("title")
    )
    return (
        "你是机器人故障 playbook 路由器。"
        "请根据用户问题，从候选 playbook title 中选择最匹配的一个。"
        "如果没有明显匹配项，就返回空字符串。"
        "只输出一个 JSON 对象，不要输出解释。\n"
        '输出格式: {"playbook_id": "", "reason": ""}\n'
        f"用户问题: {user_message}\n"
        f"候选 playbooks:\n{title_lines}"
    )
