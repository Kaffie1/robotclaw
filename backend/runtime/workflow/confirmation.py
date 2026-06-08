from __future__ import annotations

from backend.runtime.workflow.models import ConfirmationRequest


def build_confirmation_request(
    *,
    request_id: str,
    session_id: str,
    task_id: str,
    node_path: str,
    message: str,
    options: list[str] | None = None,
    resume_from_step: str = "",
    payload: dict | None = None,
) -> ConfirmationRequest:
    return ConfirmationRequest(
        request_id=request_id,
        session_id=session_id,
        task_id=task_id,
        node_path=node_path,
        message=message,
        options=list(options or []),
        resume_from_step=resume_from_step,
        payload=dict(payload or {}),
    )
