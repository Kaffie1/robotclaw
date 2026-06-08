"""检索公共函数。"""

from __future__ import annotations

from pathlib import Path
import re

from langchain_core.documents import Document

from ...shared.config import KNOWLEDGE_DIR
from ..ingestion.loader import SUPPORTED_FILE_SUFFIXES, load_documents
from ..ingestion.splitter import split_documents


def build_chunk_key(doc: Document) -> str:
    metadata = dict(getattr(doc, "metadata", {}) or {})
    return "::".join(
        [
            str(metadata.get("doc_id", "")),
            str(metadata.get("filename", "")),
            str(metadata.get("chunk_id", "")),
        ]
    )


def extract_terms(text: str) -> list[str]:
    raw = str(text or "").strip().lower()
    if not raw:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def _append(token: str) -> None:
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        terms.append(normalized)

    _append(raw)
    for token in re.split(r"[\s,.;:!?()\\[\\]{}<>\"'`|/\\\\，。；：！？（）【】《》]+", raw):
        if token:
            _append(token)
    return terms


def normalize_text(text: str) -> str:
    return str(text or "").strip().lower()


def knowledge_docs_dir() -> Path:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    return KNOWLEDGE_DIR


def iter_knowledge_files() -> list[Path]:
    root = knowledge_docs_dir()
    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_FILE_SUFFIXES
        ]
    )


def load_documents_from_knowledge_dir() -> list[Document]:
    documents: list[Document] = []
    root = knowledge_docs_dir()
    for path in iter_knowledge_files():
        try:
            docs = load_documents(path)
        except (OSError, ValueError):
            continue
        for doc in docs:
            doc.metadata.setdefault("path", str(path.relative_to(root)))
        documents.extend(split_documents(docs))
    return documents
