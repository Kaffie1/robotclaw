"""检索能力数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document


@dataclass
class RetrievalRequest:
    query: str
    top_k: int
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
class EvidenceItem:
    filename: str
    chunk_id: str
    snippet: str


@dataclass
class EvidenceResult:
    docs: list[Document] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    evidence_scores: list[float] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    context: str = ""
    confidence: float = 0.0
    low_confidence: bool = False
