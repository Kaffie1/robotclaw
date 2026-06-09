from __future__ import annotations

import re


def compare(op: str, actual, expected) -> bool:
    normalized_op = str(op or "").strip().lower()
    if normalized_op == "equals":
        return actual == expected
    if normalized_op == "not_equals":
        return actual != expected
    if normalized_op == "contains":
        return expected in actual if actual is not None else False
    if normalized_op == "not_contains":
        return expected not in actual if actual is not None else True
    if normalized_op == "greater_than":
        return _to_number(actual) is not None and _to_number(expected) is not None and _to_number(actual) > _to_number(expected)
    if normalized_op == "greater_or_equal":
        return _to_number(actual) is not None and _to_number(expected) is not None and _to_number(actual) >= _to_number(expected)
    if normalized_op == "less_than":
        return _to_number(actual) is not None and _to_number(expected) is not None and _to_number(actual) < _to_number(expected)
    if normalized_op == "less_or_equal":
        return _to_number(actual) is not None and _to_number(expected) is not None and _to_number(actual) <= _to_number(expected)
    if normalized_op == "regex_match":
        return bool(re.search(str(expected or ""), str(actual or ""), re.MULTILINE))
    if normalized_op == "not_empty":
        return bool(str(actual).strip()) if isinstance(actual, str) else bool(actual)
    if normalized_op == "is_empty":
        return not compare("not_empty", actual, expected)
    return False


def _to_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None
