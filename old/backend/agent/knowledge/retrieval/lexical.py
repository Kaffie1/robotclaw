"""词法检索通道。

当前采用本地文件知识库上的轻量词项匹配打分。
后续如果需要可以再替换成真正的 BM25 实现。
"""

from __future__ import annotations

from langchain_core.documents import Document

from ....core.config import TOP_K
from .common import build_chunk_key, extract_terms, load_documents_from_knowledge_dir, normalize_text


def load_all_documents() -> list[Document]:
    return load_documents_from_knowledge_dir()


def _lexical_score(doc: Document, query: str) -> float:
    terms = extract_terms(query)
    if not terms:
        return 0.0

    haystack = normalize_text(
        " ".join(
            [
                str(doc.page_content or ""),
                str(doc.metadata.get("title", "") or ""),
                str(doc.metadata.get("filename", "") or ""),
            ]
        )
    )
    score = 0.0
    for term in terms:
        if term in haystack:
            score += 1.0 + (haystack.count(term) * 0.1)
    return score


def retrieve_bm25_documents(
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
        score = _lexical_score(doc, query)
        if score <= 0:
            continue
        enriched = Document(
            page_content=doc.page_content,
            metadata=dict(doc.metadata or {}),
        )
        enriched.metadata["_retrieval_score"] = float(score)
        ranked.append((enriched, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    matched_docs: list[Document] = []
    seen_chunk_keys: set[str] = set()
    for doc, _score in ranked:
        chunk_key = build_chunk_key(doc)
        if chunk_key in seen_chunk_keys:
            continue
        seen_chunk_keys.add(chunk_key)
        matched_docs.append(doc)
        if len(matched_docs) >= top_k:
            break
    return matched_docs
