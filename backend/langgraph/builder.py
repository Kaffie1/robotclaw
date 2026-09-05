from __future__ import annotations

from typing import Any

from backend.gateway.models import ChatRequest
from backend.knowledge import KnowledgeService
from backend.llm import LLMRegistry
from backend.langgraph.nodes import (
    build_messages_node,
    call_chat_model_node,
    assemble_knowledge_context_node,
    decide_knowledge_response_mode_node,
    interpret_model_output_node,
    load_knowledge_source_docs_node,
    merge_knowledge_retrieval_node,
    retrieve_bm25_knowledge_node,
    retrieve_faq_knowledge_node,
    retrieve_vector_knowledge_node,
    summarize_response_node,
)
from backend.langgraph.prompts import build_summary_prompt
from backend.langgraph.router import (
    route_after_build_messages,
    route_after_interpret,
    route_after_knowledge_mode,
)
from backend.langgraph.state import ChatGraphState
from backend.memory import MemoryManager
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope, RuntimeState
from backend.runtime.workflow import publish_workflow_event
from backend.runtime.workflow.events import WorkflowEventBus
from backend.runtime.workflow.store import WorkflowStore
from backend.shared import get_logger, strip_image_attachment_summary

try:
    from langgraph.graph import END, START, StateGraph
except Exception:
    END = None
    START = None
    StateGraph = None


logger = get_logger("langgraph.builder")

def build_chat_graph() -> Any:
    if StateGraph is None or START is None or END is None:
        return None

    graph = StateGraph(ChatGraphState)
    graph.add_node("load_knowledge_source_docs", load_knowledge_source_docs_node)
    graph.add_node("retrieve_knowledge_faq", retrieve_faq_knowledge_node)
    graph.add_node("retrieve_knowledge_bm25", retrieve_bm25_knowledge_node)
    graph.add_node("retrieve_knowledge_vector", retrieve_vector_knowledge_node)
    graph.add_node("merge_knowledge_retrieval", merge_knowledge_retrieval_node)
    graph.add_node("assemble_knowledge_context", assemble_knowledge_context_node)
    graph.add_node("decide_knowledge_response_mode", decide_knowledge_response_mode_node)
    graph.add_node("build_messages", build_messages_node)
    graph.add_node("call_model", call_chat_model_node)
    graph.add_node("interpret_output", interpret_model_output_node)
    graph.add_node("summarize_response", summarize_response_node)

    graph.add_edge(START, "load_knowledge_source_docs")
    graph.add_edge("load_knowledge_source_docs", "retrieve_knowledge_faq")
    graph.add_edge("load_knowledge_source_docs", "retrieve_knowledge_bm25")
    graph.add_edge("load_knowledge_source_docs", "retrieve_knowledge_vector")
    graph.add_edge(
        [
            "retrieve_knowledge_faq",
            "retrieve_knowledge_bm25",
            "retrieve_knowledge_vector",
        ],
        "merge_knowledge_retrieval",
    )
    graph.add_edge("merge_knowledge_retrieval", "assemble_knowledge_context")
    graph.add_edge("assemble_knowledge_context", "decide_knowledge_response_mode")
    graph.add_conditional_edges(
        "decide_knowledge_response_mode",
        route_after_knowledge_mode,
        {
            "build_messages": "build_messages",
            "summarize_response": "summarize_response",
        },
    )
    graph.add_conditional_edges(
        "build_messages",
        route_after_build_messages,
        {
            "summarize_response": "summarize_response",
            "call_model": "call_model",
        },
    )
    graph.add_edge("call_model", "interpret_output")
    graph.add_conditional_edges(
        "interpret_output",
        route_after_interpret,
        {
            "done": END,
            "summarize": "summarize_response",
            "retry": "call_model",
        },
    )
    graph.add_edge("summarize_response", END)
    return graph.compile()


_CHAT_GRAPH: Any = None

STEP_TO_NODE: dict[str, str] = {
    "gateway_received": "load_knowledge_source_docs",
    "understand_query": "load_knowledge_source_docs",
    "knowledge_selection": "load_knowledge_source_docs",
    "build_messages": "build_messages",
    "call_model": "call_model",
    "interpret_output": "interpret_output",
    "tool_planning": "build_messages",
    "waiting_confirm": "summarize_response",
    "waiting_input": "summarize_response",
    "problem_analysis": "call_model",
    "solution_generation": "completed",
    "completed": "completed",
}

NODE_SEQUENCE: tuple[str, ...] = (
    "load_knowledge_source_docs",
    "retrieve_knowledge_faq",
    "retrieve_knowledge_bm25",
    "retrieve_knowledge_vector",
    "merge_knowledge_retrieval",
    "assemble_knowledge_context",
    "decide_knowledge_response_mode",
    "build_messages",
    "call_model",
    "interpret_output",
    "summarize_response",
)


def get_chat_graph() -> Any:
    global _CHAT_GRAPH
    if _CHAT_GRAPH is None:
        _CHAT_GRAPH = build_chat_graph()
    return _CHAT_GRAPH


def run_chat_graph(
    *,
    request: ChatRequest,
    envelope: RuntimeEnvelope,
    state: RuntimeState,
    connected: bool,
    knowledge_service: KnowledgeService,
    llm_registry: LLMRegistry,
    get_llm_client: Any | None,
    top_k: int,
    memory_manager: MemoryManager,
    workflow_store: WorkflowStore,
    event_bus: WorkflowEventBus,
) -> tuple[RuntimeState, DiagnosisSummary]:
    graph_state = _build_graph_state(
        request=request,
        envelope=envelope,
        state=state,
        connected=connected,
        knowledge_service=knowledge_service,
        llm_registry=llm_registry,
        get_llm_client=get_llm_client,
        top_k=top_k,
        memory_manager=memory_manager,
        workflow_store=workflow_store,
        event_bus=event_bus,
    )
    graph = get_chat_graph()
    if graph is not None:
        try:
            result = graph.invoke(graph_state)
            return result["runtime_state"], result["diagnosis"]
        except Exception as exc:
            logger.warning("LangGraph invoke 失败，降级到顺序执行 | error=%s", exc)
    result = _run_chat_graph_fallback(graph_state)
    return result["runtime_state"], result["diagnosis"]


def _build_graph_state(
    *,
    request: ChatRequest,
    envelope: RuntimeEnvelope,
    state: RuntimeState,
    connected: bool,
    knowledge_service: KnowledgeService,
    llm_registry: LLMRegistry,
    get_llm_client: Any | None,
    top_k: int,
    memory_manager: MemoryManager,
    workflow_store: WorkflowStore,
    event_bus: WorkflowEventBus,
) -> ChatGraphState:
    short_memory = memory_manager.ensure_short_memory(envelope.task.task_id)
    session_memory = memory_manager.get_session_memory(envelope.session.session_id)
    graph_state: ChatGraphState = {
        "request": request,
        "envelope": envelope,
        "runtime_state": state,
        "diagnosis": envelope.diagnosis,
        "connected": connected,
        "knowledge_service": knowledge_service,
        "get_llm_client": get_llm_client or llm_registry.get_active_client,
        "top_k": max(1, int(top_k or 4)),
        "memory_manager": memory_manager,
        "workflow_store": workflow_store,
        "event_bus": event_bus,
        "short_memory": short_memory,
        "build_summary_prompt": build_summary_prompt,
        "interaction_mode": state.interaction_mode_snapshot,
        "conversation_history": _build_recent_conversation_history(
            session_memory.chat_history,
            current_content=request.content,
            interaction_mode=state.interaction_mode_snapshot,
        ),
    }
    if "intent" in short_memory.scratchpad:
        graph_state["intent"] = short_memory.scratchpad["intent"]
    if "knowledge" in short_memory.scratchpad:
        graph_state["knowledge"] = short_memory.scratchpad["knowledge"]
    if "analysis" in short_memory.scratchpad:
        graph_state["analysis"] = short_memory.scratchpad["analysis"]
    return graph_state


def _build_recent_conversation_history(
    chat_history,
    *,
    current_content: str,
    interaction_mode: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    if str(interaction_mode or "").strip().lower() == "playbook":
        return []
    current = str(current_content or "").strip()
    history = [
        {
            "role": str(turn.role or "").strip(),
            "content": _history_content_for_model(str(turn.content or "")),
        }
        for turn in list(chat_history or [])
        if _history_content_for_model(str(turn.content or ""))
    ]
    if history and history[-1]["role"] == "user" and history[-1]["content"] == current:
        history = history[:-1]
    return history[-limit:]


def _history_content_for_model(content: str) -> str:
    return strip_image_attachment_summary(content)


def _run_chat_graph_fallback(state: ChatGraphState) -> ChatGraphState:
    runtime_state = state["runtime_state"]
    start_node = _resolve_start_node(runtime_state, state["request"].resume)

    if _should_run("load_knowledge_source_docs", start_node):
        state.update(_run_node("load_knowledge_source_docs", load_knowledge_source_docs_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("retrieve_knowledge_faq", retrieve_faq_knowledge_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("retrieve_knowledge_bm25", retrieve_bm25_knowledge_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("retrieve_knowledge_vector", retrieve_vector_knowledge_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("merge_knowledge_retrieval", merge_knowledge_retrieval_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("assemble_knowledge_context", assemble_knowledge_context_node, state))
        if _is_terminal(state):
            return state
        state.update(_run_node("decide_knowledge_response_mode", decide_knowledge_response_mode_node, state))
        if _is_terminal(state):
            return state
        next_node = route_after_knowledge_mode(state)
        if next_node == "summarize_response":
            if _should_run("summarize_response", start_node):
                state.update(_run_node("summarize_response", summarize_response_node, state))
            return state

    if _should_run("build_messages", start_node):
        state.update(_run_node("build_messages", build_messages_node, state))
        if _is_terminal(state):
            return state
        next_node = route_after_build_messages(state)
        if next_node == "summarize_response":
            if _should_run("summarize_response", start_node):
                state.update(_run_node("summarize_response", summarize_response_node, state))
            return state

    while True:
        if _should_run("call_model", start_node):
            state.update(_run_node("call_model", call_chat_model_node, state))
            if _is_terminal(state):
                return state
        if _should_run("interpret_output", start_node):
            state.update(_run_node("interpret_output", interpret_model_output_node, state))

        next_node = route_after_interpret(state)
        if next_node == "summarize":
            if _should_run("summarize_response", start_node):
                state.update(_run_node("summarize_response", summarize_response_node, state))
            return state
        if next_node != "retry":
            return state
    return state


def _should_run(node_name: str, start_node: str) -> bool:
    try:
        return NODE_SEQUENCE.index(node_name) >= NODE_SEQUENCE.index(start_node)
    except ValueError:
        return False


def _resolve_start_node(runtime_state: RuntimeState, is_resume: bool) -> str:
    if not is_resume:
        return "load_knowledge_source_docs"
    resume_from = (runtime_state.resume_from_step or "").strip()
    if resume_from in NODE_SEQUENCE:
        return resume_from
    if resume_from in STEP_TO_NODE:
        return STEP_TO_NODE[resume_from]
    return "load_knowledge_source_docs"


def _is_terminal(state: ChatGraphState) -> bool:
    runtime_state = state["runtime_state"]
    return runtime_state.interrupt_flag or runtime_state.finished or runtime_state.current_step in {"waiting_confirm", "waiting_input"}


def _run_node(node_name: str, node_fn: Any, state: ChatGraphState) -> dict[str, Any]:
    runtime_state = state["runtime_state"]
    workflow_store = state["workflow_store"]
    event_bus = state["event_bus"]
    short_memory = state["short_memory"]
    if runtime_state.interrupt_flag:
        runtime_state.current_step = "interrupted"
        runtime_state.finished = False
        runtime_state.resume_from_step = node_name
        short_memory.current_node = node_name
        workflow_store.save_runtime_state(runtime_state)
        publish_workflow_event(
            store=workflow_store,
            event_bus=event_bus,
            session_id=runtime_state.session_id,
            task_id=runtime_state.task_id,
            event_type="node.interrupted",
            payload={"node": node_name, "resume_from_step": runtime_state.resume_from_step},
        )
        return {
            "runtime_state": runtime_state,
            "short_memory": short_memory,
        }

    short_memory.current_node = node_name
    short_memory.visited_nodes.append(node_name)
    publish_workflow_event(
        store=workflow_store,
        event_bus=event_bus,
        session_id=runtime_state.session_id,
        task_id=runtime_state.task_id,
        event_type="node.started",
        payload={"node": node_name, "resume": state["request"].resume},
    )
    result = node_fn(state)
    updated_runtime = result.get("runtime_state", runtime_state)
    updated_short_memory = result.get("short_memory", short_memory)
    updated_short_memory.current_node = node_name
    workflow_store.save_runtime_state(updated_runtime)
    publish_workflow_event(
        store=workflow_store,
        event_bus=event_bus,
        session_id=updated_runtime.session_id,
        task_id=updated_runtime.task_id,
        event_type="node.completed",
        payload={
            "node": node_name,
            "current_step": updated_runtime.current_step,
            "finished": updated_runtime.finished,
        },
    )
    return result
