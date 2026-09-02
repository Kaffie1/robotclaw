"""知识检索子系统。

按上级 knowledge 项目的切分方式预留：
- embeddings: embedding 模型工厂
- vectorstore: 向量库加载与持久化入口
- retrieval: 检索通道与证据编排

当前阶段只搭好可导入的结构，不主动接入现有聊天执行链路。
"""

from .embeddings import clear_embeddings_cache, get_embeddings
from .models import (
    EmbeddingSpec,
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
    VectorRecord,
)
from .service import KnowledgeService
from .services import ingest_file, preview_split_file, rebuild_vectorstore_from_knowledge_dir
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
    RetrievalTaskRequest,
    build_chunk_key,
    compute_confidence,
    extract_terms,
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
    "EmbeddingSpec",
    "EvidenceItem",
    "EvidenceResult",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeService",
    "KnowledgeVectorStoreHandle",
    "ParallelRetrievalResult",
    "RetrievalHit",
    "RetrievalChannelResult",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalTaskRequest",
    "VectorRecord",
    "build_chunk_key",
    "build_vectorstore",
    "clear_embeddings_cache",
    "compute_confidence",
    "extract_terms",
    "get_embeddings",
    "ingest_file",
    "load_all_documents",
    "load_vectorstore",
    "preview_split_file",
    "rerank_documents",
    "rebuild_vectorstore_from_knowledge_dir",
    "reset_vectorstore",
    "retrieve_bm25_documents",
    "retrieve_faq_documents",
    "retrieve_local_keyword_documents",
    "retrieve_tag_filtered_documents",
    "retrieve_vector_documents",
    "select_evidence",
]
