from __future__ import annotations


def merge_runtime_context(base: dict | None, extra: dict | None) -> dict:
    merged = dict(base or {})
    merged.update(extra or {})
    return merged
