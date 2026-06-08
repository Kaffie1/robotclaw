from __future__ import annotations


def compare(op: str, actual, expected) -> bool:
    if op == "equals":
        return actual == expected
    if op == "contains":
        return expected in actual if actual is not None else False
    if op == "greater_than":
        return actual > expected
    return False
