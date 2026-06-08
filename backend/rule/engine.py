from __future__ import annotations

from backend.rule.models import RuleCall, RuleResult
from backend.rule.operators import compare
from backend.rule.registry import RuleRegistry
from backend.rule.resolver import resolve_path


class RuleEngine:
    def __init__(self, registry: RuleRegistry | None = None) -> None:
        self.registry = registry or RuleRegistry()

    def evaluate(self, call: RuleCall) -> RuleResult:
        spec = self.registry.get(call.rule_id)
        if spec is None:
            return RuleResult(rule_id=call.rule_id, passed=False, detail={"reason": "rule_not_found"})

        details: list[dict] = []
        passed = True
        for condition in spec.conditions:
            actual = resolve_path(call.inputs, condition.field)
            current = compare(condition.op, actual, condition.value)
            details.append({"field": condition.field, "actual": actual, "passed": current})
            if not current:
                passed = False
        return RuleResult(rule_id=call.rule_id, passed=passed, detail={"conditions": details})
