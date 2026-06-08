from __future__ import annotations

from dataclasses import asdict
from typing import Any

from langchain_core.documents import Document

from backend.knowledge import (
    build_chunk_key,
    load_all_documents,
    retrieve_bm25_documents,
    retrieve_faq_documents,
    retrieve_vector_documents,
    select_evidence,
)
from backend.runtime.models import EvidenceItem, RouteDecision
from backend.shared import TOP_K, get_logger


logger = get_logger("langgraph.knowledge")

ANSWER_HINT_KEYWORDS = {
    "代码",
    "示例",
    "例子",
    "接口",
    "参数",
    "定义",
    "文档",
    "说明",
    "怎么调用",
    "如何调用",
    "调用方式",
    "建图",
    "slam",
    "mapping",
}

ACT_HINT_KEYWORDS = {
    "帮我检查",
    "帮我看",
    "帮我执行",
    "帮我调用",
    "帮我确认",
    "现在",
    "当前",
    "机器人上",
    "是否有",
    "有没有",
    "查一下",
    "排查",
    "恢复",
    "重启",
    "执行一下",
}

FAULT_HINT_KEYWORDS = {
    "报错",
    "失败",
    "异常",
    "不通",
    "没数据",
    "没有数据",
    "无数据",
    "无法",
    "起不来",
    "连不上",
    "故障",
}


def retrieve_knowledge(knowledge_service, query: str, topic: str) -> dict[str, object]:
    del knowledge_service
    del topic
    docs = load_all_documents()
    faq_docs = retrieve_faq_documents(query=query, top_k=TOP_K, docs=docs) if docs else []
    bm25_docs = retrieve_bm25_documents(query=query, top_k=TOP_K, docs=docs) if docs else []
    try:
        vector_docs = retrieve_vector_documents(query=query, top_k=TOP_K)
    except Exception:
        vector_docs = []
    merged_docs = _merge_ranked_documents([faq_docs, bm25_docs, vector_docs])
    if not merged_docs:
        return {
            "summary": "已进入知识路径，但当前没有检索到足够相关的内容。",
            "detail": "可以直接基于现有上下文回答，或在后续补充更具体的问题后再检索。",
            "confidence": 0.0,
            "low_confidence": True,
            "context": "",
            "evidence": [],
            "citations": [],
            "channels": [],
        }
    result = select_evidence(docs=merged_docs, query=query)
    return {
        "summary": "已检索到相关知识片段",
        "detail": "；".join(item.snippet for item in result.evidence[:3]) if result.evidence else "已命中相关知识。",
        "confidence": result.confidence,
        "low_confidence": result.low_confidence,
        "context": result.context,
        "evidence": [asdict(item) for item in result.evidence],
        "citations": result.citations,
        "channels": _used_channels(faq_docs=faq_docs, bm25_docs=bm25_docs, vector_docs=vector_docs),
    }


def load_knowledge_source_docs_node(state: dict) -> dict:
    request = state["request"]
    query = str(request.content or "").strip()
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]

    runtime_state.current_step = "knowledge_selection"
    if not query:
        short_memory.scratchpad["knowledge_source_docs"] = []
        return {"runtime_state": runtime_state, "short_memory": short_memory, "knowledge_source_docs": []}

    try:
        docs = load_all_documents()
    except Exception as exc:
        logger.warning("知识源文档加载失败，跳过检索 | error=%s", exc)
        docs = []

    short_memory.scratchpad["knowledge_source_docs"] = docs
    logger.info("知识检索 Source | hits=%d | query=%s", len(docs), query[:80])
    return {"runtime_state": runtime_state, "short_memory": short_memory, "knowledge_source_docs": docs}


def retrieve_faq_knowledge_node(state: dict) -> dict:
    request = state["request"]
    source_docs = list(state.get("knowledge_source_docs") or [])
    faq_docs = retrieve_faq_documents(query=request.content, top_k=TOP_K, docs=source_docs) if source_docs else []
    logger.info("知识检索 FAQ | top_k=%d | hits=%d | query=%s", TOP_K, len(faq_docs), request.content[:80])
    return {"knowledge_faq_docs": faq_docs}


def retrieve_bm25_knowledge_node(state: dict) -> dict:
    request = state["request"]
    source_docs = list(state.get("knowledge_source_docs") or [])
    bm25_docs = retrieve_bm25_documents(query=request.content, top_k=TOP_K, docs=source_docs) if source_docs else []
    logger.info("知识检索 BM25 | top_k=%d | hits=%d | query=%s", TOP_K, len(bm25_docs), request.content[:80])
    return {"knowledge_bm25_docs": bm25_docs}


def retrieve_vector_knowledge_node(state: dict) -> dict:
    request = state["request"]
    try:
        vector_docs = retrieve_vector_documents(query=request.content, top_k=TOP_K)
    except Exception as exc:
        logger.warning("知识检索 Vector 失败，继续降级到 FAQ/BM25 | error=%s", exc)
        vector_docs = []
    logger.info("知识检索 Vector | top_k=%d | hits=%d | query=%s", TOP_K, len(vector_docs), request.content[:80])
    return {"knowledge_vector_docs": vector_docs}


def merge_knowledge_retrieval_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    request = state["request"]

    faq_docs = list(state.get("knowledge_faq_docs") or [])
    bm25_docs = list(state.get("knowledge_bm25_docs") or [])
    vector_docs = list(state.get("knowledge_vector_docs") or [])
    merged_docs = _merge_ranked_documents([faq_docs, bm25_docs, vector_docs])

    logger.info(
        "知识检索 Merge | top_k=%d | faq_hits=%d | bm25_hits=%d | vector_hits=%d | merged_hits=%d",
        TOP_K,
        len(faq_docs),
        len(bm25_docs),
        len(vector_docs),
        len(merged_docs),
    )

    if not merged_docs:
        knowledge = {
            "summary": "已进入知识路径，但当前没有检索到足够相关的内容。",
            "detail": "可以直接基于现有上下文回答，或在后续补充更具体的问题后再检索。",
            "confidence": 0.0,
            "low_confidence": True,
            "context": "",
            "evidence": [],
            "citations": [],
            "channels": [],
        }
    else:
        result = select_evidence(docs=merged_docs, query=request.content)
        knowledge = {
            "summary": "已检索到相关知识片段",
            "detail": "；".join(item.snippet for item in result.evidence[:3]) if result.evidence else "已命中相关知识。",
            "confidence": result.confidence,
            "low_confidence": result.low_confidence,
            "context": result.context,
            "evidence": [asdict(item) for item in result.evidence],
            "citations": result.citations,
            "channels": _used_channels(faq_docs=faq_docs, bm25_docs=bm25_docs, vector_docs=vector_docs),
        }

    runtime_state.knowledge_used = True
    runtime_state.knowledge_confidence = float(knowledge["confidence"])
    runtime_state.knowledge_low_confidence = bool(knowledge.get("low_confidence", False))
    runtime_state.trace.append(
        RouteDecision(
            stage="知识库检索",
            summary=str(knowledge["summary"]),
            detail=str(knowledge["detail"]),
        )
    )
    diagnosis.evidence.append(
        EvidenceItem(
            source="knowledge",
            content=str(knowledge["summary"]),
            confidence=float(knowledge["confidence"]),
        )
    )
    for item in knowledge.get("evidence", [])[:3]:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet", "")).strip()
        if not snippet:
            continue
        diagnosis.evidence.append(
            EvidenceItem(
                source="knowledge",
                content=snippet,
                confidence=float(knowledge["confidence"]),
            )
        )

    short_memory.scratchpad["knowledge"] = knowledge
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
        "knowledge": knowledge,
        "knowledge_merged_docs": merged_docs,
    }


def assemble_knowledge_context_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    diagnosis = state["diagnosis"]
    short_memory = state["short_memory"]
    knowledge = state.get("knowledge") or short_memory.scratchpad.get("knowledge") or {}
    context = str(knowledge.get("context", "") or "").strip()
    citations = list(knowledge.get("citations") or [])
    confidence = float(knowledge.get("confidence", 0.0) or 0.0)
    low_confidence = bool(knowledge.get("low_confidence", False))

    short_memory.scratchpad["knowledge_context"] = context
    short_memory.scratchpad["knowledge_citations"] = citations
    runtime_state.retrieval_result = {
        "context": context,
        "citations": citations,
        "confidence": confidence,
        "low_confidence": low_confidence,
        "channels": list(knowledge.get("channels") or []),
    }
    if context:
        diagnosis.evidence.append(
            EvidenceItem(
                source="knowledge_context",
                content=context[:300],
                confidence=confidence,
            )
        )
    return {
        "runtime_state": runtime_state,
        "diagnosis": diagnosis,
        "short_memory": short_memory,
    }


def decide_knowledge_response_mode_node(state: dict) -> dict:
    runtime_state = state["runtime_state"]
    short_memory = state["short_memory"]
    query = str(state["request"].content or "").strip().lower()
    response_mode = _detect_response_mode(query)
    short_memory.scratchpad["response_mode"] = response_mode
    runtime_state.trace.append(
        RouteDecision(
            stage="知识回答模式",
            summary="当前使用知识直答模式" if response_mode == "answer" else "当前允许进入动作/排查模式",
            detail=f"response_mode={response_mode}",
        )
    )
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "response_mode": response_mode,
    }


def retrieve_knowledge_node(state: dict) -> dict:
    state.update(load_knowledge_source_docs_node(state))
    state.update(retrieve_faq_knowledge_node(state))
    state.update(retrieve_bm25_knowledge_node(state))
    state.update(retrieve_vector_knowledge_node(state))
    state.update(merge_knowledge_retrieval_node(state))
    state.update(assemble_knowledge_context_node(state))
    state.update(decide_knowledge_response_mode_node(state))
    return state


def _merge_ranked_documents(doc_groups: list[list[Document]]) -> list[Document]:
    merged: dict[str, Document] = {}
    for docs in doc_groups:
        for doc in docs:
            chunk_key = build_chunk_key(doc)
            score = float(doc.metadata.get("_retrieval_score", 0.0) or 0.0)
            existing = merged.get(chunk_key)
            existing_score = float(existing.metadata.get("_retrieval_score", 0.0) or 0.0) if existing is not None else float("-inf")
            if existing is None or score > existing_score:
                merged[chunk_key] = doc
    return sorted(
        merged.values(),
        key=lambda item: float(item.metadata.get("_retrieval_score", 0.0) or 0.0),
        reverse=True,
    )


def _used_channels(*, faq_docs: list[Document], bm25_docs: list[Document], vector_docs: list[Document]) -> list[str]:
    channels: list[str] = []
    if faq_docs:
        channels.append("faq")
    if bm25_docs:
        channels.append("bm25")
    if vector_docs:
        channels.append("vector")
    return channels


def _detect_response_mode(query: str) -> str:
    if not query:
        return "answer"
    if any(keyword in query for keyword in ACT_HINT_KEYWORDS):
        return "act"
    if any(keyword in query for keyword in FAULT_HINT_KEYWORDS):
        return "act"
    if any(keyword in query for keyword in ANSWER_HINT_KEYWORDS):
        return "answer"
    return "answer"
