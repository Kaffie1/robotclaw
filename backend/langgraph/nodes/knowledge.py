from __future__ import annotations

from backend.knowledge import KnowledgeService
from backend.runtime.models import EvidenceItem, RouteDecision


def retrieve_knowledge(knowledge_service: KnowledgeService, topic: str) -> dict[str, str | float]:
    return knowledge_service.retrieve(topic)


def retrieve_knowledge_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    playbook = state["playbook"]

    runtime_state.current_step = "knowledge_selection"
    knowledge = retrieve_knowledge(state["knowledge_service"], str(playbook["topic"]))
    runtime_state.knowledge_used = True
    runtime_state.knowledge_confidence = float(knowledge["confidence"])
    runtime_state.trace.append(
        RouteDecision(
            stage="知识库检索",
            summary=str(knowledge["summary"]),
            detail=str(knowledge["detail"]),
        )
    )
    diagnosis.evidence.append(
        EvidenceItem(
            source="knowledge",
            content=str(knowledge["summary"]),
            confidence=float(knowledge["confidence"]),
        )
    )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "knowledge": knowledge,
    }
