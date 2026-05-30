"""检索公共函数。"""

from __future__ import annotations

from langchain_core.documents import Document


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
    return [token for token in str(text or "").strip().split() if token]
