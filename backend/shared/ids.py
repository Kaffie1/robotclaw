from __future__ import annotations

from itertools import count


_session_counter = count(1)
_task_counter = count(1)
_request_counter = count(1)
_event_counter = count(1)
_resume_counter = count(1)
_tool_call_counter = count(1)


def next_session_id() -> str:
    return f"session-{next(_session_counter)}"


def next_task_id() -> str:
    return f"task-{next(_task_counter)}"


def next_request_id() -> str:
    return f"req-{next(_request_counter)}"


def next_event_id() -> str:
    return f"evt-{next(_event_counter)}"


def next_resume_token() -> str:
    return f"resume-{next(_resume_counter)}"


def next_tool_call_id() -> str:
    return f"toolcall-{next(_tool_call_counter)}"
