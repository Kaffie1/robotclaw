from __future__ import annotations

from typing import Any, TypedDict

from backend.gateway.models import ChatRequest
from backend.knowledge import KnowledgeService
from backend.memory import MemoryManager
from backend.memory.models import ShortMemory
from backend.playbook import PlaybookEngine
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope, RuntimeState
from backend.runtime.workflow.models import ConfirmationRequest
from backend.runtime.workflow.store import WorkflowStore
from backend.runtime.workflow.events import WorkflowEventBus
from backend.tools import ToolExecutor
from backend.llm.models import LLMMessage


class ChatGraphState(TypedDict, total=False):
    request: ChatRequest
    envelope: RuntimeEnvelope
    runtime_state: RuntimeState
    diagnosis: DiagnosisSummary
    connected: bool
    playbook_engine: PlaybookEngine
    knowledge_service: KnowledgeService
    get_llm_client: Any
    tool_executor: ToolExecutor
    memory_manager: MemoryManager
    workflow_store: WorkflowStore
    event_bus: WorkflowEventBus
    short_memory: ShortMemory
    build_classify_prompt: Any
    build_route_prompt: Any
    build_planner_prompt: Any
    build_summary_prompt: Any
    conversation_history: list[dict[str, str]]
    interaction_mode: str
    intent: dict[str, Any]
    playbook: dict[str, Any]
    knowledge_source_docs: list[Any]
    knowledge_faq_docs: list[Any]
    knowledge_bm25_docs: list[Any]
    knowledge_vector_docs: list[Any]
    knowledge_merged_docs: list[Any]
    knowledge: dict[str, Any]
    response_mode: str
    analysis: dict[str, Any]
    messages: list[LLMMessage]
    response_content: str
    model_loop_count: int
    parsed_response: dict[str, Any]
    pending_commands: list[dict[str, Any]]
    result_kind: str
    tool_iteration_status: str
    final_message: str
    confirmation_request: ConfirmationRequest
