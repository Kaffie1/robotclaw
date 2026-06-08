from __future__ import annotations

from backend.runtime.workflow.models import ResumeToken


def build_resume_token(
    *,
    token: str,
    session_id: str,
    task_id: str,
    resume_from_step: str = "",
    payload: dict | None = None,
) -> ResumeToken:
    return ResumeToken(
        token=token,
        session_id=session_id,
        task_id=task_id,
        resume_from_step=resume_from_step,
        payload=dict(payload or {}),
    )
