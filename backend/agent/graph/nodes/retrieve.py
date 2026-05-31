from __future__ import annotations

from typing import Any

from ....core.config import ENABLE_RERANKER, TOP_K
from ....core.shared import append_fault_trace, logger, normalize_message_content
from ....runtime.tools import tool_registry
from ...prompts.answer import build_fault_chat_system_prompt, build_knowledge_answer_system_prompt
from ...knowledge import (
    build_chunk_key,
    load_all_documents,
    rerank_documents,
    retrieve_bm25_documents,
    retrieve_faq_documents,
    retrieve_vector_documents,
    select_evidence,
)
from ...shared.model_factory import load_chat_message_classes
from ..state import FaultChatState
from ..timing import log_stage_duration, start_stage_timer


def _empty_knowledge_state() -> FaultChatState:
    return {
        "knowledge_source_docs": [],
        "knowledge_faq_docs": [],
        "knowledge_bm25_docs": [],
        "knowledge_vector_docs": [],
        "knowledge_merged_docs": [],
        "knowledge_used": False,
        "knowledge_context": "",
        "knowledge_confidence": 0.0,
        "knowledge_low_confidence": False,
        "knowledge_citations": [],
        "response_mode": "answer",
    }


ANSWER_HINT_KEYWORDS = {
    "代码",
    "示例",
    "例子",
    "接口",
    "参数",
    "消息类型",
    "定义",
    "文档",
    "说明",
    "怎么调用",
    "如何调用",
    "调用方式",
    "ros1",
    "ros2",
    "python",
    "cpp",
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
    "ping",
    "echo",
    "list",
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


def _detect_response_mode(query: str) -> str:
    normalized_query = normalize_message_content(query).lower()
    if not normalized_query:
        return "answer"
    if any(keyword in normalized_query for keyword in ACT_HINT_KEYWORDS):
        return "act"
    if any(keyword in normalized_query for keyword in FAULT_HINT_KEYWORDS):
        return "act"
    if any(keyword in normalized_query for keyword in ANSWER_HINT_KEYWORDS):
        return "answer"
    return "answer"


def _replace_system_prompt(messages: list[Any], system_prompt: str) -> list[Any]:
    if not messages:
        return messages
    _, _, SystemMessage = load_chat_message_classes()
    updated_messages = list(messages)
    first_message = updated_messages[0]
    if first_message.__class__.__name__ == SystemMessage.__name__:
        updated_messages[0] = SystemMessage(content=system_prompt)
        return updated_messages
    return [SystemMessage(content=system_prompt), *updated_messages]


def load_knowledge_source_docs_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    if not query:
        log_stage_duration("load_knowledge_source_docs", started_at, doc_count=0, skipped=True)
        return _empty_knowledge_state()
    try:
        docs = load_all_documents()
    except Exception as exc:  # noqa: BLE001
        logger.warning("知识库加载失败，跳过知识检索降级 | error=%s", exc)
        append_fault_trace("knowledge_retrieval_error", {"stage": "load_documents", "error": str(exc)})
        log_stage_duration("load_knowledge_source_docs", started_at, doc_count=0, error=str(exc))
        return _empty_knowledge_state()
    if not docs:
        append_fault_trace("knowledge_retrieval_empty", {"query": query})
        log_stage_duration("load_knowledge_source_docs", started_at, doc_count=0)
        return _empty_knowledge_state()
    append_fault_trace("knowledge_source_loaded", {"query": query, "doc_count": len(docs)})
    log_stage_duration("load_knowledge_source_docs", started_at, doc_count=len(docs))
    return {"knowledge_source_docs": docs}


def _merge_ranked_documents(doc_groups: list[list[Any]]) -> list[Any]:
    merged: dict[str, Any] = {}
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


def _build_knowledge_feedback_message(
    *,
    query: str,
    confidence: float,
    low_confidence: bool,
    citations: list[dict[str, Any]],
    context: str,
) -> str:
    citation_lines = []
    for index, item in enumerate(citations, start=1):
        filename = normalize_message_content(item.get("filename", "")) or "unknown"
        chunk_id = normalize_message_content(item.get("chunk_id", "")) or "N/A"
        citation_lines.append(f"{index}. {filename}#{chunk_id}")
    citation_block = "\n".join(citation_lines) if citation_lines else "无"
    confidence_note = "偏低" if low_confidence else "可用"
    return (
        "【知识库检索结果】\n"
        f"查询: {query}\n"
        f"置信度: {confidence:.2f}（{confidence_note}）\n"
        f"命中文档:\n{citation_block}\n\n"
        "【知识库上下文】\n"
        f"{context}"
    ).strip()


def retrieve_faq_knowledge_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    if not query:
        log_stage_duration("retrieve_knowledge_faq", started_at, hits=0, skipped=True)
        return {"knowledge_faq_docs": []}
    all_docs = list(state.get("knowledge_source_docs") or [])
    if not all_docs:
        log_stage_duration("retrieve_knowledge_faq", started_at, hits=0, skipped=True)
        return {"knowledge_faq_docs": []}
    faq_docs = retrieve_faq_documents(query=query, top_k=TOP_K, docs=all_docs)
    logger.info("知识检索 FAQ | top_k=%d | hits=%d | query=%s", TOP_K, len(faq_docs), query[:80])
    append_fault_trace("knowledge_retrieval_faq", {"query": query, "hits": len(faq_docs)})
    log_stage_duration("retrieve_knowledge_faq", started_at, hits=len(faq_docs), top_k=TOP_K)
    return {"knowledge_faq_docs": faq_docs}


def retrieve_bm25_knowledge_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    if not query:
        log_stage_duration("retrieve_knowledge_bm25", started_at, hits=0, skipped=True)
        return {"knowledge_bm25_docs": []}
    all_docs = list(state.get("knowledge_source_docs") or [])
    if not all_docs:
        log_stage_duration("retrieve_knowledge_bm25", started_at, hits=0, skipped=True)
        return {"knowledge_bm25_docs": []}
    bm25_docs = retrieve_bm25_documents(query=query, top_k=TOP_K, docs=all_docs)
    logger.info("知识检索 BM25 | top_k=%d | hits=%d | query=%s", TOP_K, len(bm25_docs), query[:80])
    append_fault_trace("knowledge_retrieval_bm25", {"query": query, "hits": len(bm25_docs)})
    log_stage_duration("retrieve_knowledge_bm25", started_at, hits=len(bm25_docs), top_k=TOP_K)
    return {"knowledge_bm25_docs": bm25_docs}


def retrieve_vector_knowledge_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    if not query:
        log_stage_duration("retrieve_knowledge_vector", started_at, hits=0, skipped=True)
        return {"knowledge_vector_docs": []}
    try:
        vector_docs = retrieve_vector_documents(query=query, top_k=TOP_K)
    except Exception as exc:  # noqa: BLE001
        logger.warning("向量检索失败，继续使用本地词法/FAQ 结果 | error=%s", exc)
        append_fault_trace("knowledge_retrieval_error", {"stage": "vector", "error": str(exc)})
        vector_docs = []
    logger.info("知识检索 Vector | top_k=%d | hits=%d | query=%s", TOP_K, len(vector_docs), query[:80])
    append_fault_trace("knowledge_retrieval_vector", {"query": query, "hits": len(vector_docs)})
    log_stage_duration("retrieve_knowledge_vector", started_at, hits=len(vector_docs), top_k=TOP_K)
    return {
        "knowledge_vector_docs": vector_docs,
    }


def merge_knowledge_retrieval_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    faq_docs = list(state.get("knowledge_faq_docs") or [])
    bm25_docs = list(state.get("knowledge_bm25_docs") or [])
    vector_docs = list(state.get("knowledge_vector_docs") or [])
    merged_docs = _merge_ranked_documents([faq_docs, bm25_docs, vector_docs])
    if ENABLE_RERANKER:
        merged_docs = rerank_documents(merged_docs, query=query)
    append_fault_trace(
        "knowledge_retrieval_merged",
        {
            "query": query,
            "faq_hits": len(faq_docs),
            "bm25_hits": len(bm25_docs),
            "vector_hits": len(vector_docs),
            "merged_hits": len(merged_docs),
        },
    )
    logger.info(
        "知识检索 Merge | top_k=%d | faq_hits=%d | bm25_hits=%d | vector_hits=%d | merged_hits=%d",
        TOP_K,
        len(faq_docs),
        len(bm25_docs),
        len(vector_docs),
        len(merged_docs),
    )
    log_stage_duration("merge_knowledge_retrieval", started_at, merged_hits=len(merged_docs), top_k=TOP_K)
    return {"knowledge_merged_docs": merged_docs}


def assemble_knowledge_context_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    faq_docs = list(state.get("knowledge_faq_docs") or [])
    bm25_docs = list(state.get("knowledge_bm25_docs") or [])
    vector_docs = list(state.get("knowledge_vector_docs") or [])
    merged_docs = list(state.get("knowledge_merged_docs") or [])
    evidence = select_evidence(docs=merged_docs, query=query, top_k=TOP_K)
    if not evidence.docs or not evidence.context.strip():
        append_fault_trace(
            "knowledge_retrieval_empty",
            {
                "query": query,
                "faq_hits": len(faq_docs),
                "bm25_hits": len(bm25_docs),
                "vector_hits": len(vector_docs),
            },
        )
        log_stage_duration("assemble_knowledge_context", started_at, selected_hits=0, confidence=0.0)
        return _empty_knowledge_state()

    messages = list(state.get("messages") or [])
    _, HumanMessage, _ = load_chat_message_classes()
    messages.append(
        HumanMessage(
            content=_build_knowledge_feedback_message(
                query=query,
                confidence=evidence.confidence,
                low_confidence=evidence.low_confidence,
                citations=evidence.citations,
                context=evidence.context,
            )
        )
    )
    append_fault_trace(
        "knowledge_retrieval_result",
        {
            "query": query,
            "faq_hits": len(faq_docs),
            "bm25_hits": len(bm25_docs),
            "vector_hits": len(vector_docs),
            "selected_hits": len(evidence.docs),
            "confidence": evidence.confidence,
            "low_confidence": evidence.low_confidence,
            "citations": evidence.citations,
        },
    )
    logger.info(
        "知识检索 Evidence | top_k=%d | selected_hits=%d | confidence=%.2f | low_confidence=%s",
        TOP_K,
        len(evidence.docs),
        evidence.confidence,
        evidence.low_confidence,
    )
    log_stage_duration(
        "assemble_knowledge_context",
        started_at,
        selected_hits=len(evidence.docs),
        confidence=round(evidence.confidence, 4),
        low_confidence=bool(evidence.low_confidence),
    )
    return {
        "messages": messages,
        "knowledge_used": True,
        "knowledge_context": evidence.context,
        "knowledge_confidence": evidence.confidence,
        "knowledge_low_confidence": evidence.low_confidence,
        "knowledge_citations": evidence.citations,
    }


def decide_knowledge_response_mode_node(state: FaultChatState) -> FaultChatState:
    started_at = start_stage_timer()
    query = normalize_message_content(state.get("user_message", ""))
    response_mode = _detect_response_mode(query)
    messages = list(state.get("messages") or [])
    if response_mode == "answer":
        system_prompt = build_knowledge_answer_system_prompt()
    else:
        system_prompt = build_fault_chat_system_prompt(tool_registry.list_definitions())
    messages = _replace_system_prompt(messages, system_prompt)
    append_fault_trace(
        "knowledge_response_mode",
        {
            "query": query,
            "mode": response_mode,
            "knowledge_used": bool(state.get("knowledge_used")),
            "knowledge_confidence": float(state.get("knowledge_confidence", 0.0) or 0.0),
        },
    )
    log_stage_duration("decide_knowledge_response_mode", started_at, mode=response_mode)
    return {
        "messages": messages,
        "response_mode": response_mode,
    }


__all__ = [
    "assemble_knowledge_context_node",
    "decide_knowledge_response_mode_node",
    "load_knowledge_source_docs_node",
    "merge_knowledge_retrieval_node",
    "retrieve_bm25_knowledge_node",
    "retrieve_faq_knowledge_node",
    "retrieve_vector_knowledge_node",
]
