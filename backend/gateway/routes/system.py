from fastapi import APIRouter, Request

from ..support import get_session, get_session_id

router = APIRouter()


@router.get("/api/ping")
def api_ping(request: Request):
    session = get_session(request)
    return {
        "ok": True,
        "session_id": get_session_id(request),
        "connected": bool(session["client"].connected),
    }
