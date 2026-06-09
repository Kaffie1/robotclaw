from __future__ import annotations

from typing import Any


def resolve_path(payload: dict, field: str) -> Any:
    current: Any = payload
    for segment in str(field or "").split("."):
        if not segment:
            continue
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return None
    return current
