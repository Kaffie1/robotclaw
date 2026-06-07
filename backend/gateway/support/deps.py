from typing import Any

from fastapi import Request

from ...infra.container import session_store


def get_session_id(request: Request) -> str:
    return str(request.state.session_id or "")


def get_session(request: Request) -> dict[str, Any]:
    session = getattr(request.state, "session", None)
    if isinstance(session, dict):
        return session
    resolved = session_store.get(get_session_id(request))
    if not isinstance(resolved, dict):
        raise RuntimeError("当前请求缺少有效会话上下文")
    return resolved


def get_session_client(request: Request) -> Any:
    return session_store.get_client(get_session(request))


def is_session_connected(request: Request) -> bool:
    return session_store.is_connected(get_session(request))


def get_connected_session_client(request: Request) -> Any:
    client = get_session_client(request)
    client.ensure_connected()
    return client
