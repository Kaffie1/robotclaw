from typing import Any, TypedDict


class FaultRouteState(TypedDict, total=False):
    session_id: str  # 当前会话 ID
    user_message: str  # 用户本轮输入
    playbooks: list[dict[str, str]]  # 可参与路由的 playbook 列表
    selected_playbook_id: str  # 路由命中的 playbook ID
    selected_playbook_title: str  # 路由命中的 playbook 标题
    selected_playbook_type: str  # 路由命中的 workflow 类型，如 fault / normal
    reason: str  # 路由命中的原因说明
    resume_continuation: dict[str, Any] | None  # 中断恢复时携带的 continuation 信息
    prefetched_playbook_id: str  # 前端预先选中的 playbook ID
    prefetched_playbook_title: str  # 前端预先选中的 playbook 标题
    prefetched_playbook_type: str  # 前端预先选中的 workflow 类型
    prefetched_reason: str  # 前端预选 playbook 的原因


class FaultChatState(TypedDict, total=False):
    thread_id: str  # LangGraph 线程 ID，用于多轮恢复和上下文关联
    session_id: str  # 当前会话 ID
    user_message: str  # 用户本轮输入
    conversation_history: list[dict[str, str]]  # 近几轮聊天历史
    playbooks: list[dict[str, str]]  # 可参与路由的 playbook 列表
    selected_playbook_id: str  # 路由命中的 playbook ID
    selected_playbook_title: str  # 路由命中的 playbook 标题
    selected_playbook_type: str  # 路由命中的 workflow 类型，如 fault / normal
    reason: str  # 路由命中的原因说明
    prefetched_playbook_id: str  # 前端预先选中的 playbook ID
    prefetched_playbook_title: str  # 前端预先选中的 playbook 标题
    prefetched_playbook_type: str  # 前端预先选中的 workflow 类型
    prefetched_reason: str  # 前端预选 playbook 的原因
    runtime_context: dict[str, Any]  # 聊天运行时上下文
    tool_context: dict[str, Any]  # 原始工具上下文
    effective_tool_context: dict[str, Any]  # 经过恢复/确认后实际生效的工具上下文
    resume_continuation: dict[str, Any] | None  # 中断恢复时携带的 continuation 信息
    confirmation_response: str  # 用户对人工确认问题的回复
    messages: list[Any]  # 当前提供给模型的消息列表
    tool_traces: list[dict[str, Any]]  # 工具调用轨迹
    scripted_playbook: dict[str, Any] | None  # playbook 执行结果
    pending_confirmation: dict[str, Any] | None  # 待用户确认的信息
    pending_playbook_render: dict[str, Any] | None  # 待前端渲染的 playbook 信息
    playbook_render_ready: bool  # 前端是否完成 playbook 渲染
    playbook_resume_state: dict[str, Any] | None  # playbook 恢复执行所需状态
    playbook_completed: bool  # playbook 是否已经执行完成
    knowledge_source_docs: list[Any]  # 知识库加载出的原始文档列表
    knowledge_faq_docs: list[Any]  # FAQ 通道召回结果
    knowledge_bm25_docs: list[Any]  # BM25 通道召回结果
    knowledge_vector_docs: list[Any]  # 向量通道召回结果
    knowledge_merged_docs: list[Any]  # 多路召回合并后的结果
    knowledge_used: bool  # 本轮是否使用了知识库检索降级
    knowledge_context: str  # 检索得到的拼接上下文
    knowledge_confidence: float  # 检索证据置信度
    knowledge_low_confidence: bool  # 检索证据是否低置信度
    knowledge_citations: list[dict[str, Any]]  # 检索命中的引用信息
    response_mode: str  # 当前回答模式，answer=纯知识回答，act=允许继续调工具
    model_loop_count: int  # 当前模型循环调用次数
    response: Any  # 模型原始返回对象
    response_content: str  # 模型返回的文本内容
    parsed_response: dict[str, Any] | None  # 从模型文本中解析出的结构化 JSON
    pending_commands: list[dict[str, Any]]  # 待执行的工具命令列表
    final_message: str  # 最终返回给用户的消息
    result_kind: str  # 当前结果类型，如 final/clarify/tool_call/retry
