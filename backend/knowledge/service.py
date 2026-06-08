from __future__ import annotations

from dataclasses import asdict

from .retrieval import load_all_documents, retrieve_bm25_documents, select_evidence


class KnowledgeService:
    def retrieve(self, query: str, topic: str = "general") -> dict[str, object]:
        del topic
        docs = load_all_documents()
        matched = retrieve_bm25_documents(query=query, docs=docs)
        if not matched:
            return {
                "summary": "已进入知识路径，但当前没有检索到足够相关的内容。",
                "detail": "可以直接基于现有上下文回答，或在后续补充更具体的问题后再检索。",
                "confidence": 0.0,
                "low_confidence": True,
                "context": "",
                "evidence": [],
                "citations": [],
            }
        result = select_evidence(docs=matched, query=query)
        return {
            "summary": "已检索到相关知识片段",
            "detail": "；".join(item.snippet for item in result.evidence[:3]) if result.evidence else "已命中相关知识。",
            "confidence": result.confidence,
            "low_confidence": result.low_confidence,
            "context": result.context,
            "evidence": [asdict(item) for item in result.evidence],
            "citations": result.citations,
        }
