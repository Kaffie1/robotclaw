"""词法检索通道。

预留 BM25 / 关键词召回边界。当前仓库还没有知识库文档装载链路，
这里先保持与上级项目相近的接口形态，后续再接真实文档源。
"""

from __future__ import annotations

from langchain_core.documents import Document

from .common import build_chunk_key


def load_all_documents(kb_name: str) -> list[Document]:
    del kb_name
    return []


def retrieve_bm25_documents(
    query: str,
    kb_name: str,
    top_k: int = 5,
    exclude_chunk_keys: set[str] | None = None,
    docs: list[Document] | None = None,
) -> list[Document]:
    del query
    del kb_name

    exclude_chunk_keys = exclude_chunk_keys or set()
    source_docs = list(docs or [])
    matched_docs: list[Document] = []
    seen_chunk_keys: set[str] = set()
    for doc in source_docs:
        chunk_key = build_chunk_key(doc)
        if chunk_key in seen_chunk_keys or chunk_key in exclude_chunk_keys:
            continue
        seen_chunk_keys.add(chunk_key)
        matched_docs.append(doc)
        if len(matched_docs) >= top_k:
            break
    return matched_docs
