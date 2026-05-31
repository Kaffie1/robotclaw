"""元数据过滤检索通道。"""

from __future__ import annotations

from langchain_core.documents import Document

from ....core.config import TOP_K


def retrieve_tag_filtered_documents(
    query: str,
    top_k: int = TOP_K,
    exclude_chunk_keys: set[str] | None = None,
    docs: list[Document] | None = None,
) -> list[Document]:
    del query
    del top_k
    del exclude_chunk_keys
    del docs
    return []
