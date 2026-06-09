from __future__ import annotations

from backend.rule.models import RuleSpec
from backend.rule.loader import load_rules


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, RuleSpec] = {}

    def register(self, spec: RuleSpec) -> None:
        self._rules[spec.rule_id] = spec

    def get(self, rule_id: str) -> RuleSpec | None:
        return self._rules.get(rule_id)

    def load_from_file(self, rule_file: str) -> None:
        for spec in load_rules(rule_file):
            self.register(spec)
