import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ...agent import run_fault_chat_graph
from ...agent.graph.nodes.classify import load_catalog_node
from ...agent.graph.nodes.route import resolve_playbook_route
from ...runtime.workflow.playbook_state import (
    build_matched_playbook_payload_by_id,
    clear_live_playbook_state,
    get_live_playbook_state,
    reset_live_playbook_execution,
    stream_live_playbook_events,
)
from ...core.config import MAX_TASK_ITEMS
from ...core.models import ToolCallPayload
from ...core.shared import logger
from ...infra.container import task_manager
from ...runtime.tools import tool_registry
from ...runtime.workflow.confirmation import append_chat_history_turn, get_chat_history, reset_chat_state
from ..support import get_session, get_session_id, summarize_playbook_execution

router = APIRouter()


@router.post("/api/chat")
async def api_chat(request: Request):
    session = get_session(request)
    session_id = get_session_id(request)
    body = await request.json()
    message = str(body.get("message") or "").strip()
    continuation = body.get("continuation")
    history = body.get("history")
    route_selection = body.get("route_selection")
    if continuation is not None and not isinstance(continuation, dict):
        return JSONResponse(content={"ok": False, "error": "continuation 必须是对象"}, status_code=400)
    if history is not None and not isinstance(history, list):
        return JSONResponse(content={"ok": False, "error": "history 必须是数组"}, status_code=400)
    if route_selection is not None and not isinstance(route_selection, dict):
        return JSONResponse(content={"ok": False, "error": "route_selection 必须是对象"}, status_code=400)
    if continuation is None and not message:
        return JSONResponse(content={"ok": False, "error": "消息内容不能为空"}, status_code=400)
    if isinstance(continuation, dict):
        user_message = str(continuation.get("user_message") or "").strip()
        if not user_message:
            return JSONResponse(content={"ok": False, "error": "continuation 缺少 user_message"}, status_code=400)
        tool_context: dict[str, Any] = {"session_id": session_id, **dict(continuation.get("tool_context") or {})}
    else:
        user_message = message
        tool_context = {"session_id": session_id}
    last_config = session.get("last_config") or {}
    route_selection_payload = build_matched_playbook_payload_by_id(str((route_selection or {}).get("playbook_id") or "").strip())
    continuation_kind = str((continuation or {}).get("kind") or "").strip() if isinstance(continuation, dict) else ""
    if isinstance(continuation, dict):
        raw_resume_state = continuation.get("resume_state")
        resume_completed_nodes = raw_resume_state.get("completed_nodes") if isinstance(raw_resume_state, dict) else {}
        logger.info(
            "API /api/chat 收到 continuation | session_id=%s | kind=%s | has_resume_state=%s | resume_completed_nodes=%s",
            session_id,
            continuation_kind,
            isinstance(raw_resume_state, dict),
            sorted(str(key) for key in (resume_completed_nodes or {}).keys()) if isinstance(resume_completed_nodes, dict) else [],
        )
    if not isinstance(continuation, dict):
        if route_selection_payload:
            reset_live_playbook_execution(session_id=session_id, playbook=route_selection_payload)
        else:
            clear_live_playbook_state(session_id=session_id)
    result = await asyncio.to_thread(
        run_fault_chat_graph,
        user_message,
        runtime_context={
            "connected": bool(session["client"].connected),
            "host": str(last_config.get("host") or ""),
            "port": str(last_config.get("port") or ""),
            "username": str(last_config.get("username") or ""),
            "preferred_root": str(session.get("preferred_root") or "/"),
            "recent_tasks": task_manager.list_tasks_for_owner(session_id, MAX_TASK_ITEMS),
        },
        tool_context=tool_context,
        conversation_history=[
            {
                "role": str(item.get("role") or "").strip(),
                "content": str(item.get("content") or "").strip(),
            }
            for item in (history or [])
            if isinstance(item, dict)
        ],
        resume_continuation=continuation if isinstance(continuation, dict) else None,
        confirmation_response=message if continuation_kind == "playbook_confirmation" else "",
        prefetched_playbook_id=str((route_selection or {}).get("playbook_id") or "").strip(),
        prefetched_playbook_title=str((route_selection or {}).get("playbook_title") or "").strip(),
        prefetched_reason=str((route_selection or {}).get("reason") or "").strip(),
    )
    append_chat_history_turn(
        tool_context,
        user_message=user_message,
        assistant_message=str(result.get("message") or ""),
    )
    logger.info(
        "API /api/chat 返回流程图状态 | session_id=%s | summary=%s",
        session_id,
        json.dumps(summarize_playbook_execution(result.get("playbook_execution")), ensure_ascii=False),
    )
    return {"ok": True, **result}


@router.post("/api/chat/reset")
def api_chat_reset(request: Request):
    session_id = get_session_id(request)
    reset_chat_state({"session_id": session_id})
    clear_live_playbook_state(session_id=session_id)
    return {"ok": True, "message": "聊天上下文已清空"}


@router.get("/api/chat/history")
def api_chat_history(request: Request):
    return {"ok": True, "history": get_chat_history({"session_id": get_session_id(request)})}


@router.post("/api/chat/route")
async def api_chat_route(request: Request):
    session_id = get_session_id(request)
    body = await request.json()
    message = str(body.get("message") or "").strip()
    continuation = body.get("continuation")
    if continuation is not None and not isinstance(continuation, dict):
        return JSONResponse(content={"ok": False, "error": "continuation 必须是对象"}, status_code=400)
    if not continuation and not message:
        return JSONResponse(content={"ok": False, "error": "消息内容不能为空"}, status_code=400)
    route_state = {
        **load_catalog_node({}),
        "session_id": session_id,
        "user_message": message,
        "resume_continuation": continuation if isinstance(continuation, dict) else None,
    }
    route_result = await asyncio.to_thread(resolve_playbook_route, route_state, publish=True)
    playbook_id = str(route_result.get("selected_playbook_id") or "").strip()
    playbook_title = str(route_result.get("selected_playbook_title") or "").strip()
    reason = str(route_result.get("reason") or "").strip()
    playbook_payload = build_matched_playbook_payload_by_id(playbook_id)
    return {
        "ok": True,
        "route_selection": {
            "playbook_id": playbook_id,
            "playbook_title": playbook_title,
            "reason": reason,
        },
        "playbook": playbook_payload,
    }


@router.get("/api/chat/state")
async def api_chat_state(request: Request):
    session_id = get_session_id(request)
    raw_since_version = request.query_params.get("since_version", "0")
    try:
        since_version = max(int(raw_since_version), 0)
    except ValueError:
        since_version = 0
    payload = get_live_playbook_state(session_id=session_id, since_version=since_version)
    logger.info(
        "API /api/chat/state 返回流程图状态 | session_id=%s | since_version=%s | summary=%s",
        session_id,
        since_version,
        json.dumps(summarize_playbook_execution(payload.get("playbook_execution")), ensure_ascii=False),
    )
    return {"ok": True, **payload}


@router.get("/api/chat/events")
async def api_chat_events(request: Request):
    session_id = get_session_id(request)
    raw_since_version = request.query_params.get("since_version", "0")
    try:
        since_version = max(int(raw_since_version), 0)
    except ValueError:
        since_version = 0
    logger.info("API /api/chat/events 建立SSE | session_id=%s | since_version=%s", session_id, since_version)
    return StreamingResponse(
        stream_live_playbook_events(session_id=session_id, since_version=since_version),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/agent/tools")
def api_agent_tools():
    return {"ok": True, "items": tool_registry.list_definitions()}


@router.post("/api/agent/tool-call")
def api_agent_tool_call(payload: ToolCallPayload, request: Request):
    result = tool_registry.call_tool(
        payload.name,
        payload.arguments,
        {"session_id": get_session_id(request)},
    )
    return {"ok": True, "result": result}
