from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.rule.models import RuleCondition, RuleSpec
from backend.rule.schema import validate_rule_spec


def load_rules(rule_file: str | Path | None) -> list[RuleSpec]:
    if not rule_file:
        return []
    path = Path(rule_file)
    if not path.exists() or not path.is_file():
        return []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        payload = yaml.safe_load(raw_text)
    except Exception:
        payload = yaml.safe_load(_sanitize_legacy_yaml(raw_text))
    if not isinstance(payload, dict):
        return []
    rules = payload.get("rules")
    if not isinstance(rules, dict):
        return []
    loaded: list[RuleSpec] = []
    for rule_id, raw in rules.items():
        if not isinstance(raw, dict):
            continue
        spec = RuleSpec(
            rule_id=str(rule_id).strip(),
            name=str(raw.get("name") or rule_id).strip(),
            conditions=_parse_conditions(raw),
            definition=dict(raw),
        )
        validate_rule_spec(spec)
        loaded.append(spec)
    return loaded


def _parse_conditions(raw: dict[str, Any]) -> list[RuleCondition]:
    if isinstance(raw.get("conditions"), list):
        return [
            RuleCondition(
                field=str(item.get("field") or "").strip(),
                op=str(item.get("op") or "").strip(),
                value=item.get("value"),
                extract=dict(item.get("extract") or {}) if isinstance(item.get("extract"), dict) else {},
                cast=str(item.get("cast") or "").strip(),
            )
            for item in raw.get("conditions") or []
            if isinstance(item, dict)
        ]
    return [
        RuleCondition(
            field=str(raw.get("field") or "").strip(),
            op=str(raw.get("op") or "").strip(),
            value=raw.get("value"),
            extract=dict(raw.get("extract") or {}) if isinstance(raw.get("extract"), dict) else {},
            cast=str(raw.get("cast") or "").strip(),
        )
    ]


def _sanitize_legacy_yaml(raw_text: str) -> str:
    lines: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if ':"' not in stripped and ': "' not in stripped:
            lines.append(line)
            continue
        if "\\" not in line:
            lines.append(line)
            continue
        prefix, quote, suffix = line.partition('"')
        if not quote or '"' not in suffix:
            lines.append(line)
            continue
        value, quote2, tail = suffix.rpartition('"')
        if not quote2:
            lines.append(line)
            continue
        lines.append(f"{prefix}'{value}'{tail}")
    return "\n".join(lines)
