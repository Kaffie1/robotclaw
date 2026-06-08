from __future__ import annotations

from dataclasses import asdict

from backend.runtime.workflow.models import WorkflowEvent
from backend.shared import next_event_id, now_iso


class WorkflowEventBus:
    def __init__(self) -> None:
        self._events: list[WorkflowEvent] = []

    def publish(self, event: WorkflowEvent) -> None:
        self._events.append(event)

    def drain_payloads(self) -> list[dict]:
        payloads = [asdict(event) for event in self._events]
        self._events.clear()
        return payloads


def publish_workflow_event(
    *,
    store,
    event_bus: WorkflowEventBus,
    session_id: str,
    task_id: str,
    event_type: str,
    payload: dict | None = None,
) -> WorkflowEvent:
    event = WorkflowEvent(
        event_id=next_event_id(),
        session_id=session_id,
        task_id=task_id,
        event_type=event_type,
        payload=dict(payload or {}),
        created_at=now_iso(),
    )
    store.append_event(event)
    event_bus.publish(event)
    return event
