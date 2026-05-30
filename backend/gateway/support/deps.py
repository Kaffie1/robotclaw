from typing import Any

from fastapi import Request


def get_session(request: Request) -> dict[str, Any]:
    return request.state.session


def get_session_id(request: Request) -> str:
    return str(request.state.session_id or "")
