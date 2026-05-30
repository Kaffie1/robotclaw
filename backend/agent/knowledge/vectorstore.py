"""本地文件型知识库向量库。

不依赖数据库服务，所有索引都直接持久化到本地目录：
- index.json: embedding 指纹和 chunk 数据

当前实现目标：
- build/load/reset 生命周期完整
- 与 `agent.knowledge.retrieval.vector` 对接
- 保持简单、可调试、可迁移
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil

from langchain_core.documents import Document

from .embeddings import get_embeddings


@dataclass
class KnowledgeVectorRecord:
    page_content: str
    metadata: dict
    embedding: list[float]


@dataclass
class KnowledgeVectorStoreHandle:
    """知识库向量库句柄。"""

    kb_name: str
    persist_dir: Path
    records: list[KnowledgeVectorRecord]
    embedding_signature: dict[str, str]

    def as_documents(self) -> list[Document]:
        return [
            Document(
                page_content=record.page_content,
                metadata=dict(record.metadata or {}),
            )
            for record in self.records
        ]


_VECTORSTORE_CACHE: dict[str, KnowledgeVectorStoreHandle] = {}


def _vector_db_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[3]
    configured = str(os.getenv("VECTOR_DB_DIR") or (base_dir / "data" / "vectorstore")).strip()
    return Path(configured)


def _embedding_provider() -> str:
    return str(os.getenv("EMBEDDING_PROVIDER") or "openai").strip().lower() or "openai"


def _embedding_model() -> str:
    return str(os.getenv("EMBEDDING_MODEL") or "text-embedding-3-large").strip() or "text-embedding-3-large"


def _embedding_base_url() -> str:
    return str(os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()


def _current_embedding_signature() -> dict[str, str]:
    provider = _embedding_provider()
    return {
        "provider": provider,
        "model": _embedding_model(),
        "base_url": _embedding_base_url() if provider != "huggingface" else "",
    }


def _index_path(kb_name: str) -> Path:
    return get_vectorstore_dir(kb_name) / "index.json"


def get_vectorstore_dir(kb_name: str) -> Path:
    normalized = str(kb_name or "default").strip() or "default"
    return _vector_db_dir() / normalized


def ensure_vectorstore_dir(kb_name: str) -> Path:
    target = get_vectorstore_dir(kb_name)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _record_from_document(doc: Document, embedding: list[float]) -> KnowledgeVectorRecord:
    return KnowledgeVectorRecord(
        page_content=doc.page_content,
        metadata=dict(getattr(doc, "metadata", {}) or {}),
        embedding=[float(value) for value in embedding],
    )


def _dump_handle(handle: KnowledgeVectorStoreHandle) -> None:
    ensure_vectorstore_dir(handle.kb_name)
    payload = {
        "kb_name": handle.kb_name,
        "embedding_signature": handle.embedding_signature,
        "records": [asdict(record) for record in handle.records],
    }
    _index_path(handle.kb_name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_payload(kb_name: str) -> dict:
    index_path = _index_path(kb_name)
    if not index_path.exists():
        raise RuntimeError(f"知识库 '{kb_name}' 尚未构建本地向量索引。")
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"知识库 '{kb_name}' 的本地向量索引损坏：{exc}") from exc


def _restore_handle(kb_name: str, payload: dict) -> KnowledgeVectorStoreHandle:
    stored_signature = dict(payload.get("embedding_signature") or {})
    current_signature = _current_embedding_signature()
    if stored_signature and stored_signature != current_signature:
        raise RuntimeError(
            f"知识库 '{kb_name}' 的 embedding 配置与当前环境不一致。"
        )
    records = [
        KnowledgeVectorRecord(
            page_content=str(item.get("page_content", "") or ""),
            metadata=dict(item.get("metadata") or {}),
            embedding=[float(value) for value in list(item.get("embedding") or [])],
        )
        for item in list(payload.get("records") or [])
    ]
    return KnowledgeVectorStoreHandle(
        kb_name=kb_name,
        persist_dir=get_vectorstore_dir(kb_name),
        records=records,
        embedding_signature=stored_signature or current_signature,
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
    kb_name: str,
    replace_existing: bool = True,
) -> KnowledgeVectorStoreHandle:
    normalized_kb = str(kb_name or "default").strip() or "default"
    if replace_existing:
        reset_vectorstore(kb_name=normalized_kb, silent=True)

    ensure_vectorstore_dir(normalized_kb)
    embeddings = get_embeddings()
    texts = [chunk.page_content for chunk in chunks]
    vectors = embeddings.embed_documents(texts) if texts else []
    records = [
        _record_from_document(chunk, vector)
        for chunk, vector in zip(chunks, vectors)
    ]
    handle = KnowledgeVectorStoreHandle(
        kb_name=normalized_kb,
        persist_dir=get_vectorstore_dir(normalized_kb),
        records=records,
        embedding_signature=_current_embedding_signature(),
    )
    _dump_handle(handle)
    _VECTORSTORE_CACHE[normalized_kb] = handle
    return handle


def load_vectorstore(kb_name: str) -> KnowledgeVectorStoreHandle:
    normalized_kb = str(kb_name or "default").strip() or "default"
    cached = _VECTORSTORE_CACHE.get(normalized_kb)
    if cached is not None:
        return cached
    payload = _load_payload(normalized_kb)
    handle = _restore_handle(normalized_kb, payload)
    _VECTORSTORE_CACHE[normalized_kb] = handle
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


def reset_vectorstore(*, kb_name: str, silent: bool = False) -> None:
    normalized_kb = str(kb_name or "default").strip() or "default"
    _VECTORSTORE_CACHE.pop(normalized_kb, None)
    persist_dir = get_vectorstore_dir(normalized_kb)
    if persist_dir.exists():
        shutil.rmtree(persist_dir, ignore_errors=True)
    elif not silent:
        raise RuntimeError(f"知识库 '{normalized_kb}' 的本地向量目录不存在。")
