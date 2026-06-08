from __future__ import annotations

from typing import Any, TypedDict

from backend.gateway.models import ChatRequest
from backend.knowledge import KnowledgeService
from backend.llm import LLMClient
from backend.memory import MemoryManager
from backend.memory.models import ShortMemory
from backend.playbook import PlaybookEngine
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope, RuntimeState
from backend.tools import ToolExecutor


class ChatGraphState(TypedDict, total=False):
    request: ChatRequest
    envelope: RuntimeEnvelope
    runtime_state: RuntimeState
    diagnosis: DiagnosisSummary
    connected: bool
    playbook_engine: PlaybookEngine
    knowledge_service: KnowledgeService
    llm_client: LLMClient
    tool_executor: ToolExecutor
    memory_manager: MemoryManager
    short_memory: ShortMemory
    build_classify_prompt: Any
    build_route_prompt: Any
    build_planner_prompt: Any
    build_summary_prompt: Any
    intent: dict[str, Any]
    playbook: dict[str, Any]
    knowledge: dict[str, Any]
    analysis: dict[str, Any]
