"""证据选择编排器。"""

from __future__ import annotations

from langchain_core.documents import Document

from ...shared.config import LOW_CONFIDENCE_THRESHOLD, TOP_K
from .common import extract_terms
from .models import EvidenceItem, EvidenceResult
from .reranker import compute_confidence


def extract_evidence_snippet(doc: Document, query: str) -> str:
    lines = [line.strip() for line in doc.page_content.splitlines() if line.strip()]
    terms = extract_terms(query)
    for line in lines:
        if any(term in line for term in terms):
            return line[:200]
    if lines:
        return lines[0][:200]
    return doc.page_content[:200]


def select_evidence(
    *,
    docs: list[Document],
    query: str,
    top_k: int = TOP_K,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> EvidenceResult:
    evidence_docs = docs[:top_k]
    evidence_scores = [float(doc.metadata.get("_retrieval_score", 0.0) or 0.0) for doc in evidence_docs]
    evidence = [
        EvidenceItem(
            filename=str(doc.metadata.get("filename", "unknown")),
            chunk_id=str(doc.metadata.get("chunk_id", "N/A")),
            snippet=extract_evidence_snippet(doc, query),
        )
        for doc in evidence_docs
    ]
    context = "\n\n".join(doc.page_content for doc in evidence_docs)
    citations = [
        {
            "filename": item.filename,
            "chunk_id": item.chunk_id,
        }
        for item in evidence
    ]
    confidence = compute_confidence(evidence_docs, query)
    low_confidence = bool(evidence_docs) and confidence < low_confidence_threshold
    return EvidenceResult(
        docs=evidence_docs,
        evidence=evidence,
        evidence_scores=evidence_scores,
        citations=citations,
        context=context,
        confidence=confidence,
        low_confidence=low_confidence,
    )
