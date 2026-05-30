"""FAQ 检索通道。

适合固定问答、短问法和标题型召回。当前先保留接口与返回结构。
"""

from __future__ import annotations

from langchain_core.documents import Document


def retrieve_faq_documents(
    query: str,
    kb_name: str,
    top_k: int = 5,
    exclude_chunk_keys: set[str] | None = None,
    docs: list[Document] | None = None,
) -> list[Document]:
    del query
    del kb_name
    del top_k
    del exclude_chunk_keys
    del docs
    return []


def retrieve_local_keyword_documents(
    query: str,
    kb_name: str,
    top_k: int = 5,
    docs: list[Document] | None = None,
) -> list[Document]:
    del query
    del kb_name
    del top_k
    del docs
    return []
