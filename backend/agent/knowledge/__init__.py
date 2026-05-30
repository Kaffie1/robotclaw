"""知识检索子系统。

按上级 knowledge 项目的切分方式预留：
- embeddings: embedding 模型工厂
- vectorstore: 向量库加载与持久化入口
- retrieval: 检索通道与证据编排

当前阶段只搭好可导入的结构，不主动接入现有聊天执行链路。
"""

from .embeddings import clear_embeddings_cache, get_embeddings, set_embedding_device_override
from .vectorstore import (
    KnowledgeVectorStoreHandle,
    build_vectorstore,
    load_vectorstore,
    reset_vectorstore,
)
from .retrieval import (
    EvidenceItem,
    EvidenceResult,
    ParallelRetrievalResult,
    RetrievalChannelResult,
    RetrievalRequest,
    build_chunk_key,
    compute_confidence,
    load_all_documents,
    rerank_documents,
    retrieve_bm25_documents,
    retrieve_faq_documents,
    retrieve_local_keyword_documents,
    retrieve_tag_filtered_documents,
    retrieve_vector_documents,
    select_evidence,
)

__all__ = [
    "EvidenceItem",
    "EvidenceResult",
    "KnowledgeVectorStoreHandle",
    "ParallelRetrievalResult",
    "RetrievalChannelResult",
    "RetrievalRequest",
    "build_chunk_key",
    "build_vectorstore",
    "clear_embeddings_cache",
    "compute_confidence",
    "get_embeddings",
    "load_all_documents",
    "load_vectorstore",
    "rerank_documents",
    "reset_vectorstore",
    "retrieve_bm25_documents",
    "retrieve_faq_documents",
    "retrieve_local_keyword_documents",
    "retrieve_tag_filtered_documents",
    "retrieve_vector_documents",
    "select_evidence",
    "set_embedding_device_override",
]
