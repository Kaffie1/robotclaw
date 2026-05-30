from __future__ import annotations

from typing import Any

from ....core.config import OPENAI_CHAT_MODEL
from ....core.shared import append_fault_trace, extract_json_payload, logger, normalize_message_content
from ....runtime.playbooks.loader import find_playbook_by_id
from ....runtime.workflow.playbook_state import build_matched_playbook_payload, publish_live_playbook_state
from ...prompts.route import build_fault_route_prompt
from ...shared.model_factory import build_router_model, invoke_chat_model
from ..state import FaultChatState, FaultRouteState

try:
    from langgraph.types import interrupt
except Exception:
    interrupt = None


def _publish_selected_playbook(
    playbooks: list[dict[str, Any]] | None,
    selected_playbook_id: str,
    *,
    session_id: str = "",
) -> None:
    normalized_playbook_id = normalize_message_content(selected_playbook_id)
    if not normalized_playbook_id:
        return
    selected_playbook = find_playbook_by_id(normalized_playbook_id, workflow_type="fault")
    if not isinstance(selected_playbook, dict):
        selected_playbook = next(
            (
                playbook
                for playbook in (playbooks or [])
                if normalize_message_content(playbook.get("id", "")) == normalized_playbook_id
            ),
            None,
        )
    logger.info(
        "已向前端发布路由命中的流程图 | playbook_id=%s | has_root=%s",
        normalized_playbook_id,
        bool(isinstance(selected_playbook, dict) and isinstance(selected_playbook.get("root"), dict)),
    )
    publish_live_playbook_state(
        session_id=session_id,
        playbook=build_matched_playbook_payload(selected_playbook),
    )


def resolve_playbook_route(state: FaultRouteState, *, publish: bool = True) -> FaultRouteState:
    session_id = normalize_message_content(state.get("session_id", ""))
    continuation = state.get("resume_continuation")
    if isinstance(continuation, dict):
        continuation_kind = normalize_message_content(continuation.get("kind", ""))
        selected_playbook_id = normalize_message_content(continuation.get("playbook_id", ""))
        selected_playbook_title = normalize_message_content(continuation.get("playbook_title", ""))
        reason = normalize_message_content(continuation.get("reason", "")) or "继续执行人工确认后的 playbook"
        if selected_playbook_id and not selected_playbook_title:
            for item in state.get("playbooks") or []:
                if item.get("id") == selected_playbook_id:
                    selected_playbook_title = normalize_message_content(item.get("title", ""))
                    break
        if publish and continuation_kind != "playbook_confirmation":
            _publish_selected_playbook(state.get("playbooks"), selected_playbook_id, session_id=session_id)
        return {
            "selected_playbook_id": selected_playbook_id,
            "selected_playbook_title": selected_playbook_title,
            "reason": reason,
        }
    prefetched_playbook_id = normalize_message_content(state.get("prefetched_playbook_id", ""))
    if prefetched_playbook_id:
        prefetched_playbook_title = normalize_message_content(state.get("prefetched_playbook_title", ""))
        prefetched_reason = normalize_message_content(state.get("prefetched_reason", ""))
        if publish:
            _publish_selected_playbook(state.get("playbooks"), prefetched_playbook_id, session_id=session_id)
        return {
            "selected_playbook_id": prefetched_playbook_id,
            "selected_playbook_title": prefetched_playbook_title,
            "reason": prefetched_reason,
        }

    user_message = normalize_message_content(state.get("user_message", ""))
    playbooks = state.get("playbooks") or []
    if not user_message or not playbooks:
        return {
            "selected_playbook_id": "",
            "selected_playbook_title": "",
            "reason": "",
        }

    llm = build_router_model()
    prompt = build_fault_route_prompt(user_message, playbooks)
    logger.info("LLM 路由模型开始调用 | model=%s | candidate_count=%d", OPENAI_CHAT_MODEL, len(playbooks))
    append_fault_trace(
        "route_model_input",
        {
            "model": OPENAI_CHAT_MODEL,
            "user_message": user_message,
            "candidate_count": len(playbooks),
            "prompt": prompt,
        },
    )
    response = invoke_chat_model(llm, prompt, model=OPENAI_CHAT_MODEL)
    raw_content = getattr(response, "content", "")
    logger.info("LLM 路由模型返回 | model=%s", OPENAI_CHAT_MODEL)
    append_fault_trace(
        "route_model_output",
        {
            "model": OPENAI_CHAT_MODEL,
            "response": raw_content,
        },
    )
    parsed = extract_json_payload(raw_content)
    selected_playbook_id = normalize_message_content(parsed.get("playbook_id", "")) if parsed else ""
    reason = normalize_message_content(parsed.get("reason", "")) if parsed else ""
    selected_title = ""
    for item in playbooks:
        if item.get("id") == selected_playbook_id:
            selected_title = normalize_message_content(item.get("title", ""))
            break
    if not selected_title:
        selected_playbook_id = ""
    append_fault_trace(
        "route_model_decision",
        {
            "selected_playbook_id": selected_playbook_id,
            "selected_playbook_title": selected_title,
            "reason": reason,
            "parsed": parsed,
        },
    )
    if publish:
        _publish_selected_playbook(playbooks, selected_playbook_id, session_id=session_id)
    return {
        "selected_playbook_id": selected_playbook_id,
        "selected_playbook_title": selected_title,
        "reason": reason,
    }


def route_playbook_node(state: FaultRouteState) -> FaultRouteState:
    return resolve_playbook_route(state, publish=True)


def wait_for_playbook_render_node(state: FaultChatState) -> FaultChatState:
    selected_playbook_id = normalize_message_content(state.get("selected_playbook_id", ""))
    if not selected_playbook_id:
        return {"playbook_render_ready": True}
    resume_continuation = state.get("resume_continuation")
    continuation_kind = normalize_message_content((resume_continuation or {}).get("kind", "")) if isinstance(resume_continuation, dict) else ""
    if continuation_kind == "playbook_confirmation":
        logger.info("人工确认恢复时跳过流程图重新渲染等待 | playbook_id=%s", selected_playbook_id)
        return {"playbook_render_ready": True}

    playbook = find_playbook_by_id(selected_playbook_id, workflow_type="fault")
    pending_playbook_render = {
        "type": "playbook_render_ready",
        "playbook_id": selected_playbook_id,
        "playbook_title": normalize_message_content(state.get("selected_playbook_title", "")),
        "reason": normalize_message_content(state.get("reason", "")),
        "message": "流程图已准备好，等待前端确认加载完成后继续执行。",
        "playbook": build_matched_playbook_payload(playbook),
    }
    if interrupt is None:
        logger.info("langgraph interrupt 不可用，跳过前端渲染等待 | playbook_id=%s", selected_playbook_id)
        return {"playbook_render_ready": True}
    logger.info("等待前端流程图加载完成（interrupt） | playbook_id=%s", selected_playbook_id)
    resume_value = interrupt(pending_playbook_render)
    logger.info("前端流程图已加载完成，继续执行 | playbook_id=%s | resume_value=%s", selected_playbook_id, bool(resume_value))
    return {"playbook_render_ready": True}


__all__ = ["resolve_playbook_route", "route_playbook_node", "wait_for_playbook_render_node"]
