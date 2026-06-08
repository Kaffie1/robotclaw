from __future__ import annotations

from backend.rule.models import RuleSpec


def validate_rule_spec(spec: RuleSpec) -> None:
    if not spec.rule_id.strip():
        raise ValueError("rule_id is required")
