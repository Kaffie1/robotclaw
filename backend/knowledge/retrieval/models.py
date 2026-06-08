"""检索能力数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document

from ..models import RetrievalHit, RetrievalRequest, RetrievalResult


@dataclass
class RetrievalTaskRequest(RetrievalRequest):
    exclude_chunk_keys: set[str] = field(default_factory=set)
    all_docs: list[Document] = field(default_factory=list)


@dataclass
class RetrievalChannelResult:
    channel: str
    docs: list[Document] = field(default_factory=list)
    error: str = ""


@dataclass
class ParallelRetrievalResult:
    channels: dict[str, RetrievalChannelResult] = field(default_factory=dict)


@dataclass
class EvidenceItem(RetrievalHit):
    pass


@dataclass
class EvidenceResult(RetrievalResult):
    docs: list[Document] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    evidence_scores: list[float] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
