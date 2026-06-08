from __future__ import annotations

from typing import Any

from backend.gateway.models import ChatRequest
from backend.knowledge import KnowledgeService
from backend.llm import LLMClient
from backend.langgraph.nodes import (
    analyze_problem_node,
    check_robot_node,
    classify_query_node,
    enter_playbook_node,
    match_playbook_node,
    plan_tools_node,
    retrieve_knowledge_node,
    summarize_response_node,
)
from backend.langgraph.prompts import build_classify_prompt, build_planner_prompt, build_route_prompt, build_summary_prompt
from backend.langgraph.router import route_after_match, route_after_tool_planning
from backend.langgraph.state import ChatGraphState
from backend.memory import MemoryManager
from backend.playbook import PlaybookEngine
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope, RuntimeState
from backend.tools import ToolExecutor

try:
    from langgraph.graph import END, START, StateGraph
except Exception:
    END = None
    START = None
    StateGraph = None


def build_chat_graph() -> Any:
    if StateGraph is None or START is None or END is None:
        return None

    graph = StateGraph(ChatGraphState)
    graph.add_node("classify_query", classify_query_node)
    graph.add_node("match_playbook", match_playbook_node)
    graph.add_node("playbook_execution", enter_playbook_node)
    graph.add_node("knowledge_selection", retrieve_knowledge_node)
    graph.add_node("tool_planning", plan_tools_node)
    graph.add_node("robot_check", check_robot_node)
    graph.add_node("problem_analysis", analyze_problem_node)
    graph.add_node("solution_generation", summarize_response_node)

    graph.add_edge(START, "classify_query")
    graph.add_edge("classify_query", "match_playbook")
    graph.add_conditional_edges(
        "match_playbook",
        route_after_match,
        {
            "playbook_execution": "playbook_execution",
            "knowledge_selection": "knowledge_selection",
        },
    )
    graph.add_edge("playbook_execution", "tool_planning")
    graph.add_edge("knowledge_selection", "tool_planning")
    graph.add_conditional_edges(
        "tool_planning",
        route_after_tool_planning,
        {
            "robot_check": "robot_check",
            "problem_analysis": "problem_analysis",
        },
    )
    graph.add_edge("robot_check", "problem_analysis")
    graph.add_edge("problem_analysis", "solution_generation")
    graph.add_edge("solution_generation", END)
    return graph.compile()


_CHAT_GRAPH: Any = None


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
    playbook_engine: PlaybookEngine,
    knowledge_service: KnowledgeService,
    llm_client: LLMClient,
    tool_executor: ToolExecutor,
    memory_manager: MemoryManager,
) -> tuple[RuntimeState, DiagnosisSummary]:
    graph = get_chat_graph()
    if graph is not None:
        graph_state = _build_graph_state(
            request=request,
            envelope=envelope,
            state=state,
            connected=connected,
            playbook_engine=playbook_engine,
            knowledge_service=knowledge_service,
            llm_client=llm_client,
            tool_executor=tool_executor,
            memory_manager=memory_manager,
        )
        result = graph.invoke(graph_state)
        return result["runtime_state"], result["diagnosis"]
    graph_state = _build_graph_state(
        request=request,
        envelope=envelope,
        state=state,
        connected=connected,
        playbook_engine=playbook_engine,
        knowledge_service=knowledge_service,
        llm_client=llm_client,
        tool_executor=tool_executor,
        memory_manager=memory_manager,
    )
    result = _run_chat_graph_fallback(graph_state)
    return result["runtime_state"], result["diagnosis"]


def _build_graph_state(
    *,
    request: ChatRequest,
    envelope: RuntimeEnvelope,
    state: RuntimeState,
    connected: bool,
    playbook_engine: PlaybookEngine,
    knowledge_service: KnowledgeService,
    llm_client: LLMClient,
    tool_executor: ToolExecutor,
    memory_manager: MemoryManager,
) -> ChatGraphState:
    short_memory = memory_manager.ensure_short_memory(envelope.task.task_id)
    return {
        "request": request,
        "envelope": envelope,
        "runtime_state": state,
        "diagnosis": envelope.diagnosis,
        "connected": connected,
        "playbook_engine": playbook_engine,
        "knowledge_service": knowledge_service,
        "llm_client": llm_client,
        "tool_executor": tool_executor,
        "memory_manager": memory_manager,
        "short_memory": short_memory,
        "build_classify_prompt": build_classify_prompt,
        "build_route_prompt": build_route_prompt,
        "build_planner_prompt": build_planner_prompt,
        "build_summary_prompt": build_summary_prompt,
    }


def _run_chat_graph_fallback(state: ChatGraphState) -> ChatGraphState:
    state.update(classify_query_node(state))
    state.update(match_playbook_node(state))

    next_node = route_after_match(state)
    if next_node == "playbook_execution":
        state.update(enter_playbook_node(state))
    if next_node == "knowledge_selection":
        state.update(retrieve_knowledge_node(state))

    state.update(plan_tools_node(state))
    next_node = route_after_tool_planning(state)
    if next_node == "robot_check":
        state.update(check_robot_node(state))

    state.update(analyze_problem_node(state))
    state.update(summarize_response_node(state))
    return state
