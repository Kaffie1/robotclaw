from __future__ import annotations

import re
from typing import Any

from backend.rule.models import RuleCall, RuleCondition, RuleResult
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

        details: list[dict[str, Any]] = []
        passed = self._evaluate_definition(spec.definition or {}, call.inputs, details)
        return RuleResult(rule_id=call.rule_id, passed=passed, detail={"conditions": details})

    def _evaluate_definition(self, definition: dict[str, Any], inputs: dict[str, Any], details: list[dict[str, Any]]) -> bool:
        op = str(definition.get("op") or "").strip().lower()
        if op == "and":
            children = [item for item in definition.get("conditions") or [] if isinstance(item, dict)]
            results = [self._evaluate_definition(child, inputs, details) for child in children]
            return all(results) if results else False
        if op == "or":
            children = [item for item in definition.get("conditions") or [] if isinstance(item, dict)]
            results = [self._evaluate_definition(child, inputs, details) for child in children]
            return any(results) if results else False
        condition = RuleCondition(
            field=str(definition.get("field") or "").strip(),
            op=op,
            value=definition.get("value"),
            extract=dict(definition.get("extract") or {}) if isinstance(definition.get("extract"), dict) else {},
            cast=str(definition.get("cast") or "").strip(),
        )
        return self._evaluate_condition(condition, inputs, details)

    def _evaluate_condition(self, condition: RuleCondition, inputs: dict[str, Any], details: list[dict[str, Any]]) -> bool:
        actual = resolve_path(inputs, condition.field)
        extracted = actual
        if condition.extract:
            matched, extracted = self._extract_value(actual, condition.extract)
            if not matched:
                details.append({"field": condition.field, "actual": actual, "passed": False, "reason": "extract_failed"})
                return False
        actual_value = self._cast_value(extracted, condition.cast)
        expected_value = self._resolve_expected(condition.value, inputs)
        passed = compare(condition.op, actual_value, expected_value)
        details.append(
            {
                "field": condition.field,
                "actual": actual_value,
                "expected": expected_value,
                "op": condition.op,
                "passed": passed,
            }
        )
        return passed

    def _resolve_expected(self, value: Any, inputs: dict[str, Any]) -> Any:
        if isinstance(value, dict) and "from_context" in value:
            return resolve_path(inputs, str(value.get("from_context") or "").strip())
        return value

    def _extract_value(self, value: Any, extract: dict[str, Any]) -> tuple[bool, Any]:
        if str(extract.get("type") or "regex").strip().lower() != "regex":
            return False, None
        pattern = str(extract.get("pattern") or "").strip()
        if not pattern:
            return False, None
        group = int(extract.get("group", 1) or 1)
        flags = re.IGNORECASE if bool(extract.get("ignore_case")) else 0
        matched = re.search(pattern, str(value or ""), flags)
        if matched is None:
            return False, None
        try:
            return True, matched.group(group)
        except IndexError:
            return False, None

    def _cast_value(self, value: Any, cast: str) -> Any:
        normalized = str(cast or "").strip().lower()
        if normalized in {"", "raw", "auto", "string", "str", "text"}:
            return value if normalized not in {"string", "str", "text"} else "" if value is None else str(value)
        if normalized in {"number", "float", "int"}:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        if normalized in {"bool", "boolean"}:
            text = str(value or "").strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
            return None
        return value
