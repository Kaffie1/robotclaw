"""向量检索通道。"""

from __future__ import annotations

from langchain_core.documents import Document

from ..vectorstore import load_vectorstore, search_vectorstore
from .common import build_chunk_key


def retrieve_vector_documents(
    query: str,
    kb_name: str,
    top_k: int = 5,
    exclude_chunk_keys: set[str] | None = None,
    docs: list[Document] | None = None,
    query_bundle=None,
) -> list[Document]:
    del docs
    del query_bundle

    exclude_chunk_keys = exclude_chunk_keys or set()
    handle = load_vectorstore(kb_name)
    deduped_docs: list[Document] = []
    seen_chunk_keys: set[str] = set()
    for doc, score in search_vectorstore(handle=handle, query=query, top_k=top_k + len(exclude_chunk_keys)):
        doc.metadata["_retrieval_score"] = float(score)
        chunk_key = build_chunk_key(doc)
        if chunk_key in seen_chunk_keys or chunk_key in exclude_chunk_keys:
            continue
        seen_chunk_keys.add(chunk_key)
        deduped_docs.append(doc)
    return deduped_docs[:top_k]
