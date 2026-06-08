from __future__ import annotations


def resolve_path(payload: dict, field: str):
    current = payload
    for segment in field.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current
