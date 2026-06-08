from __future__ import annotations

from backend.knowledge import KnowledgeService


def retrieve_knowledge(knowledge_service: KnowledgeService, topic: str) -> dict[str, str | float]:
    return knowledge_service.retrieve(topic)
