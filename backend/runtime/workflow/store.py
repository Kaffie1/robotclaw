from __future__ import annotations

from dataclasses import replace
from threading import RLock

from backend.runtime.models import RuntimeState
from backend.runtime.workflow.models import ConfirmationRequest, ResumeToken, WorkflowEvent


class WorkflowStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._runtime_states: dict[str, RuntimeState] = {}
        self._resume_tokens: dict[str, ResumeToken] = {}
        self._confirmations: dict[str, ConfirmationRequest] = {}
        self._events: dict[str, list[WorkflowEvent]] = {}

    def save_runtime_state(self, state: RuntimeState) -> None:
        with self._lock:
            self._runtime_states[state.task_id] = replace(state)

    def get_runtime_state(self, task_id: str) -> RuntimeState | None:
        with self._lock:
            state = self._runtime_states.get(task_id)
            return replace(state) if state else None

    def save_resume_token(self, token: ResumeToken) -> None:
        with self._lock:
            self._resume_tokens[token.token] = token

    def get_resume_token(self, token: str) -> ResumeToken | None:
        with self._lock:
            return self._resume_tokens.get(token)

    def delete_resume_token(self, token: str) -> None:
        with self._lock:
            self._resume_tokens.pop(token, None)

    def save_confirmation(self, request: ConfirmationRequest) -> None:
        with self._lock:
            self._confirmations[request.task_id] = request

    def get_confirmation(self, task_id: str) -> ConfirmationRequest | None:
        with self._lock:
            return self._confirmations.get(task_id)

    def clear_confirmation(self, task_id: str) -> None:
        with self._lock:
            self._confirmations.pop(task_id, None)

    def append_event(self, event: WorkflowEvent) -> None:
        with self._lock:
            self._events.setdefault(event.task_id, []).append(event)

    def list_events(self, task_id: str) -> list[WorkflowEvent]:
        with self._lock:
            return list(self._events.get(task_id, []))
