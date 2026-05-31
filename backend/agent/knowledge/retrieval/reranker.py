"""检索结果重排。"""

from __future__ import annotations

from langchain_core.documents import Document

from ....core.config import RERANKER_MAX_CANDIDATES


def rerank_documents(
    docs: list[Document],
    query: str,
    max_candidates: int | None = RERANKER_MAX_CANDIDATES,
) -> list[Document]:
    del query
    if max_candidates is None or max_candidates <= 0:
        return list(docs)
    return list(docs)[:max_candidates]


def compute_confidence(docs: list[Document], query: str) -> float:
    del query
    if not docs:
        return 0.0
    top_score = float(docs[0].metadata.get("_retrieval_score", 0.0) or 0.0)
    if top_score:
        return max(0.0, min(1.0, top_score))
    return 0.5
