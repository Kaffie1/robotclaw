from fastapi import APIRouter, Request

from ..support import get_session_id, is_session_connected

router = APIRouter()


@router.get("/api/ping")
def api_ping(request: Request):
    return {
        "ok": True,
        "session_id": get_session_id(request),
        "connected": is_session_connected(request),
    }
