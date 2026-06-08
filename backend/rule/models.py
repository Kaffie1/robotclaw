from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleCondition:
    field: str
    op: str
    value: Any = None


@dataclass
class RuleSpec:
    rule_id: str
    name: str
    conditions: list[RuleCondition] = field(default_factory=list)


@dataclass
class RuleCall:
    rule_id: str
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleResult:
    rule_id: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)
