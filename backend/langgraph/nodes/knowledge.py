from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backend.langgraph.prompts.execution_mode import build_execution_mode_prompt
from langchain_core.documents import Document

from backend.knowledge import (
    build_chunk_key,
    load_all_documents,
    retrieve_bm25_documents,
    retrieve_faq_documents,
    retrieve_vector_documents,
    select_evidence,
)
from backend.llm import parse_execution_mode_output
from backend.runtime.models import EvidenceItem, RouteDecision
from backend.shared import TOP_K, get_logger


logger = get_logger("langgraph.knowledge")

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
    query = str(state["request"].content or "").strip()
    knowledge = state.get("knowledge") or short_memory.scratchpad.get("knowledge") or {}
    history_text = _format_history(state.get("conversation_history") or [])
    interaction_mode = str(runtime_state.interaction_mode_snapshot or "").strip().lower()
    response_mode = "answer"
    summary = "当前使用知识直答模式"
    detail = "response_mode=answer"
    analysis = None
    if interaction_mode == "playbook":
        analysis = {
            "summary": "当前模式仅执行 playbook，本轮不会进入知识检索或工具执行。",
            "detail": "如果需要知识问答或自动执行，请切换到 qa 或 agent 模式。",
        }
        short_memory.scratchpad["response_mode"] = response_mode
        short_memory.scratchpad["execution_mode_source"] = "mode_forced"
        short_memory.scratchpad["execution_mode_result"] = {
            "mode": response_mode,
            "summary": summary,
            "detail": detail,
        }
        short_memory.scratchpad["analysis"] = analysis
        runtime_state.trace.append(
            RouteDecision(
                stage="知识回答模式",
                summary=summary,
                detail="interaction_mode=playbook -> force answer",
            )
        )
        return {
            "runtime_state": runtime_state,
            "short_memory": short_memory,
            "response_mode": response_mode,
            "analysis": analysis,
        }
    if interaction_mode == "qa":
        short_memory.scratchpad["response_mode"] = response_mode
        short_memory.scratchpad["execution_mode_source"] = "mode_forced"
        short_memory.scratchpad["execution_mode_result"] = {
            "mode": response_mode,
            "summary": summary,
            "detail": detail,
        }
        runtime_state.trace.append(
            RouteDecision(
                stage="知识回答模式",
                summary=summary,
                detail="interaction_mode=qa -> force answer",
            )
        )
        return {
            "runtime_state": runtime_state,
            "short_memory": short_memory,
            "response_mode": response_mode,
        }
    prompt = build_execution_mode_prompt(
        query,
        knowledge_context=str(knowledge.get("context", "") or ""),
        history_text=history_text,
        connected=bool(state.get("connected", False)),
    )
    try:
        response = state["get_llm_client"]().invoke_schema(
            prompt=prompt,
            schema_parser=parse_execution_mode_output,
            metadata={"node": "decide_execution_mode"},
        )
        response_mode = response.parsed["mode"]
        summary = (
            "当前使用知识直答模式"
            if response_mode == "answer"
            else "当前允许进入动作/排查模式" if response_mode == "act" else "当前建议先澄清问题"
        )
        detail = str(response.parsed.get("detail") or f"response_mode={response_mode}")
        short_memory.scratchpad["execution_mode_source"] = "llm"
        short_memory.scratchpad["execution_mode_result"] = response.parsed
    except Exception:
        short_memory.scratchpad["execution_mode_source"] = "fallback"
        short_memory.scratchpad["execution_mode_result"] = {
            "mode": response_mode,
            "summary": summary,
            "detail": detail,
        }
        logger.warning(
            "知识执行模式 Decision fallback | mode=%s | query=%s",
            response_mode,
            query[:80],
        )
    logger.info(
        "知识执行模式 Decision | source=%s | mode=%s | summary=%s | detail=%s | query=%s",
        short_memory.scratchpad.get("execution_mode_source", "unknown"),
        response_mode,
        summary[:80],
        detail[:160],
        query[:80],
    )
    short_memory.scratchpad["response_mode"] = response_mode
    runtime_state.trace.append(
        RouteDecision(
            stage="知识回答模式",
            summary=summary,
            detail=detail,
        )
    )
    return {
        "runtime_state": runtime_state,
        "short_memory": short_memory,
        "response_mode": response_mode,
        "analysis": analysis,
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


def _format_history(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
