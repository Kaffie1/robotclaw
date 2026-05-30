"""元数据过滤检索通道。"""

from __future__ import annotations

from langchain_core.documents import Document


def retrieve_tag_filtered_documents(
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
