from __future__ import annotations

from dataclasses import asdict

from backend.runtime.workflow.models import WorkflowEvent


class WorkflowEventBus:
    def __init__(self) -> None:
        self._events: list[WorkflowEvent] = []

    def publish(self, event: WorkflowEvent) -> None:
        self._events.append(event)

    def drain_payloads(self) -> list[dict]:
        payloads = [asdict(event) for event in self._events]
        self._events.clear()
        return payloads
