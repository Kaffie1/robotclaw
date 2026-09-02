"""FAQ 检索通道。

适合固定问答、短问法和标题型召回。
"""

from __future__ import annotations

from langchain_core.documents import Document

from ...shared.config import TOP_K
from .common import build_chunk_key, extract_terms, normalize_text


def _faq_score(doc: Document, query: str) -> float:
    terms = extract_terms(query)
    if not terms:
        return 0.0

    title = normalize_text(str(doc.metadata.get("title", "") or ""))
    filename = normalize_text(str(doc.metadata.get("filename", "") or ""))
    content = normalize_text(str(doc.page_content or ""))
    score = 0.0
    for term in terms:
        if term in title:
            score += 3.0
        if term in filename:
            score += 6.0 + (filename.count(term) * 0.5)
        if term in content:
            score += 0.5
    return score


def retrieve_faq_documents(
    query: str,
    top_k: int = TOP_K,
    exclude_chunk_keys: set[str] | None = None,
    docs: list[Document] | None = None,
) -> list[Document]:
    exclude_chunk_keys = exclude_chunk_keys or set()
    source_docs = list(docs or [])
    ranked: list[tuple[Document, float]] = []
    for doc in source_docs:
        chunk_key = build_chunk_key(doc)
        if chunk_key in exclude_chunk_keys:
            continue
        score = _faq_score(doc, query)
        if score <= 0:
            continue
        enriched = Document(
            page_content=doc.page_content,
            metadata=dict(doc.metadata or {}),
        )
        enriched.metadata["_retrieval_score"] = float(score)
        ranked.append((enriched, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [doc for doc, _score in ranked[:top_k]]


def retrieve_local_keyword_documents(
    query: str,
    top_k: int = TOP_K,
    docs: list[Document] | None = None,
) -> list[Document]:
    return retrieve_faq_documents(query=query, top_k=top_k, docs=docs)
