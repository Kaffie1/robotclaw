"""本地文件型单知识库向量库。

不依赖数据库服务，所有索引都直接持久化到一个本地目录：
- index.json: embedding 指纹和 chunk 数据

当前实现目标：
- build/load/reset 生命周期完整
- 默认只有一个知识库，不再做多库分片
- 与 `agent.knowledge.retrieval.vector` 对接
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil

from langchain_core.documents import Document

from ..shared.config import EMBEDDING_BASE_URL, EMBEDDING_MODEL, EMBEDDING_PROVIDER, VECTOR_DB_DIR
from .embeddings import get_embeddings
from .models import EmbeddingSpec, VectorRecord


@dataclass
class KnowledgeVectorRecord:
    page_content: str
    metadata: dict
    embedding: list[float]


@dataclass
class KnowledgeVectorStoreHandle:
    """知识库向量库句柄。"""

    persist_dir: Path
    records: list[KnowledgeVectorRecord]
    embedding_signature: EmbeddingSpec

    def as_documents(self) -> list[Document]:
        return [
            Document(
                page_content=record.page_content,
                metadata=dict(record.metadata or {}),
            )
            for record in self.records
        ]


_VECTORSTORE_CACHE: KnowledgeVectorStoreHandle | None = None


def _vector_db_dir() -> Path:
    return VECTOR_DB_DIR


def _embedding_provider() -> str:
    return EMBEDDING_PROVIDER


def _embedding_model() -> str:
    return EMBEDDING_MODEL


def _embedding_base_url() -> str:
    return EMBEDDING_BASE_URL


def _current_embedding_signature() -> dict[str, str]:
    provider = _embedding_provider()
    return EmbeddingSpec(
        provider=provider,
        model=_embedding_model(),
        base_url=_embedding_base_url() if provider != "huggingface" else "",
    )


def _index_path() -> Path:
    return get_vectorstore_dir() / "index.json"


def get_vectorstore_dir() -> Path:
    return _vector_db_dir()


def ensure_vectorstore_dir() -> Path:
    target = get_vectorstore_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _record_from_document(doc: Document, embedding: list[float]) -> KnowledgeVectorRecord:
    return KnowledgeVectorRecord(
        page_content=doc.page_content,
        metadata=dict(getattr(doc, "metadata", {}) or {}),
        embedding=[float(value) for value in embedding],
    )


def _dump_handle(handle: KnowledgeVectorStoreHandle) -> None:
    ensure_vectorstore_dir()
    payload = {
        "embedding_signature": asdict(handle.embedding_signature),
        "records": [asdict(record) for record in handle.records],
    }
    _index_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_payload() -> dict:
    index_path = _index_path()
    if not index_path.exists():
        raise RuntimeError("默认知识库尚未构建本地向量索引。")
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"默认知识库的本地向量索引损坏：{exc}") from exc


def _restore_handle(payload: dict) -> KnowledgeVectorStoreHandle:
    stored_signature_payload = dict(payload.get("embedding_signature") or {})
    stored_signature = EmbeddingSpec(
        provider=str(stored_signature_payload.get("provider", "") or ""),
        model=str(stored_signature_payload.get("model", "") or ""),
        base_url=str(stored_signature_payload.get("base_url", "") or ""),
    )
    current_signature = _current_embedding_signature()
    if (
        stored_signature.provider
        or stored_signature.model
        or stored_signature.base_url
    ) and stored_signature != current_signature:
        raise RuntimeError("默认知识库的 embedding 配置与当前环境不一致。")
    records = [
        KnowledgeVectorRecord(
            page_content=str(item.get("page_content", "") or ""),
            metadata=dict(item.get("metadata") or {}),
            embedding=[float(value) for value in list(item.get("embedding") or [])],
        )
        for item in list(payload.get("records") or [])
    ]
    return KnowledgeVectorStoreHandle(
        persist_dir=get_vectorstore_dir(),
        records=records,
        embedding_signature=(
            stored_signature
            if (stored_signature.provider or stored_signature.model or stored_signature.base_url)
            else current_signature
        ),
    )


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = _normalize_vector(left)
    right_norm = _normalize_vector(right)
    return float(sum(l * r for l, r in zip(left_norm, right_norm)))


def build_vectorstore(
    chunks: list[Document],
    replace_existing: bool = True,
) -> KnowledgeVectorStoreHandle:
    global _VECTORSTORE_CACHE
    if replace_existing:
        reset_vectorstore(silent=True)

    ensure_vectorstore_dir()
    embeddings = get_embeddings()
    texts = [chunk.page_content for chunk in chunks]
    vectors = embeddings.embed_documents(texts) if texts else []
    records = [
        _record_from_document(chunk, vector)
        for chunk, vector in zip(chunks, vectors)
    ]
    handle = KnowledgeVectorStoreHandle(
        persist_dir=get_vectorstore_dir(),
        records=records,
        embedding_signature=_current_embedding_signature(),
    )
    _dump_handle(handle)
    _VECTORSTORE_CACHE = handle
    return handle


def load_vectorstore() -> KnowledgeVectorStoreHandle:
    global _VECTORSTORE_CACHE
    if _VECTORSTORE_CACHE is not None:
        return _VECTORSTORE_CACHE
    payload = _load_payload()
    handle = _restore_handle(payload)
    _VECTORSTORE_CACHE = handle
    return handle


def search_vectorstore(
    *,
    handle: KnowledgeVectorStoreHandle,
    query: str,
    top_k: int,
) -> list[tuple[Document, float]]:
    if not query.strip():
        return []
    embeddings = get_embeddings()
    query_vector = [float(value) for value in embeddings.embed_query(query)]
    ranked: list[tuple[Document, float]] = []
    for record in handle.records:
        score = cosine_similarity(query_vector, record.embedding)
        document = Document(
            page_content=record.page_content,
            metadata=dict(record.metadata or {}),
        )
        ranked.append((document, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[: max(1, top_k)]


def reset_vectorstore(*, silent: bool = False) -> None:
    global _VECTORSTORE_CACHE
    _VECTORSTORE_CACHE = None
    persist_dir = get_vectorstore_dir()
    if persist_dir.exists():
        shutil.rmtree(persist_dir, ignore_errors=True)
    elif not silent:
        raise RuntimeError("默认知识库的本地向量目录不存在。")
