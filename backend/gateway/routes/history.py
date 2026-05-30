from fastapi import APIRouter, Request

from ...core.config import MAX_TASK_ITEMS
from ...core.models import ApiError
from ...runtime.operations.services import create_history_rollback_runner
from ...infra.container import history_store, task_manager
from ..support import get_session, get_session_id

router = APIRouter()


@router.get("/api/tasks")
def api_tasks(request: Request, limit: int = MAX_TASK_ITEMS):
    owner_id = get_session_id(request)
    tasks = task_manager.list_tasks_for_owner(owner_id, limit=limit)
    return {"ok": True, "tasks": tasks}


@router.get("/api/tasks/{task_id}")
def api_task_detail(task_id: str, request: Request):
    owner_id = get_session_id(request)
    task = task_manager.get_task_for_owner(task_id, owner_id)
    if not task:
        raise ApiError("任务不存在", status_code=404)
    return {"ok": True, "task": task}


@router.post("/api/tasks/{task_id}/continue")
async def api_task_continue(task_id: str, request: Request):
    owner_id = get_session_id(request)
    body = await request.json()
    message = str(body.get("message") or "").strip()
    if not message:
        raise ApiError("确认输入不能为空", status_code=400)
    task = task_manager.continue_task(task_id, message, owner_id=owner_id)
    if not task:
        raise ApiError("任务不存在或当前不处于等待确认状态", status_code=404)
    return {"ok": True, "task": task}


@router.get("/api/history")
def api_history(request: Request, limit: int = 20):
    return {"ok": True, "history": history_store.list_entries(limit=limit, owner_id=get_session_id(request))}


@router.post("/api/history/{entry_id}/rollback")
def api_history_rollback(entry_id: int, request: Request):
    entry = history_store.get_entry(entry_id, owner_id=get_session_id(request))
    if not entry:
        raise ApiError("历史记录不存在", status_code=404)
    title, runner = create_history_rollback_runner(get_session(request), entry)
    return {
        "ok": True,
        "task": task_manager.create_task(
            "rollback",
            title,
            {"source_history_id": entry_id, "operation_type": entry["operation_type"]},
            runner,
            owner_id=get_session_id(request),
        ),
    }
