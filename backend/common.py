from __future__ import annotations

from datetime import datetime
from itertools import count


_session_counter = count(1)
_task_counter = count(1)
_request_counter = count(1)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def next_session_id() -> str:
    return f"session-{next(_session_counter)}"


def next_task_id() -> str:
    return f"task-{next(_task_counter)}"


def next_request_id() -> str:
    return f"req-{next(_request_counter)}"


def infer_title(content: str, default: str) -> str:
    text = " ".join(content.split()).strip()
    if not text:
        return default
    return text[:18] + ("..." if len(text) > 18 else "")
