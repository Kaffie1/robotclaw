from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.playbook.models import BTNodeSpec, ConditionRuleRef, PlaybookMeta, PlaybookSpec
from backend.playbook.schema import validate_playbook_spec


def default_playbook_roots() -> list[Path]:
    base_dir = Path(__file__).resolve().parent.parent.parent
    return [
        base_dir / "playbooks",
        base_dir / "old" / "workflows",
    ]


def load_playbooks(*, roots: list[Path] | None = None, category: str | None = None) -> list[PlaybookSpec]:
    discovered: dict[str, PlaybookSpec] = {}
    for root in roots or default_playbook_roots():
        if not root.exists():
            continue
        for playbook_file in sorted(root.rglob("playbook.yaml")):
            for spec in _load_from_file(playbook_file):
                if category and spec.meta.category != category:
                    continue
                discovered.setdefault(spec.meta.playbook_id, spec)
    return list(discovered.values())


def find_playbook_by_id(playbook_id: str, *, roots: list[Path] | None = None) -> PlaybookSpec | None:
    normalized_id = str(playbook_id or "").strip()
    if not normalized_id:
        return None
    for spec in load_playbooks(roots=roots):
        if spec.meta.playbook_id == normalized_id:
            return spec
    return None


def get_playbook_catalog(*, roots: list[Path] | None = None, category: str | None = None) -> list[dict[str, str]]:
    return [
        {
            "id": spec.meta.playbook_id,
            "title": spec.meta.name,
            "type": spec.meta.category,
        }
        for spec in load_playbooks(roots=roots, category=category)
    ]


def _load_from_file(playbook_file: Path) -> list[PlaybookSpec]:
    try:
        payload = yaml.safe_load(playbook_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    playbooks = payload.get("playbooks")
    if isinstance(playbooks, list):
        return [_parse_playbook(item, playbook_file, payload) for item in playbooks if isinstance(item, dict)]
    return [_parse_playbook(payload, playbook_file, payload)]


def _parse_playbook(raw: dict[str, Any], playbook_file: Path, envelope: dict[str, Any]) -> PlaybookSpec:
    playbook_id = str(raw.get("id") or raw.get("playbook_id") or "").strip()
    category = str(raw.get("type") or raw.get("category") or raw.get("workflow_type") or "fault").strip().lower() or "fault"
    tags = _normalize_tags(raw.get("tags"))
    meta = PlaybookMeta(
        playbook_id=playbook_id,
        name=str(raw.get("title") or raw.get("name") or playbook_id).strip(),
        version=str(raw.get("version") or envelope.get("version") or "v1").strip() or "v1",
        category=category,
        description=str(raw.get("description") or envelope.get("description") or "").strip(),
    )
    setattr(meta, "source_path", str(playbook_file))
    setattr(meta, "rules_source_path", str(playbook_file.with_name("rules.yaml")))
    spec = PlaybookSpec(
        meta=meta,
        root=_parse_node(raw.get("root") or {}, node_id="root"),
        input_fields=sorted(_extract_input_fields(raw.get("context_schema"))),
        tags=tags,
    )
    setattr(spec, "execution_notes", _normalize_text_list(raw.get("execution_notes")))
    setattr(spec, "escalation_notes", _normalize_text_list(raw.get("escalation_notes")))
    setattr(spec, "context_schema", dict(raw.get("context_schema") or {}) if isinstance(raw.get("context_schema"), dict) else {})
    validate_playbook_spec(spec)
    return spec


def _parse_node(raw: dict[str, Any], *, node_id: str) -> BTNodeSpec:
    name = str(raw.get("name") or raw.get("display_name") or node_id).strip() or node_id
    node_type = str(raw.get("type") or "result").strip().lower() or "result"
    children_raw = raw.get("children") if isinstance(raw.get("children"), list) else []
    rule = _parse_rule_ref(raw)
    node = BTNodeSpec(
        node_id=str(raw.get("node_id") or name).strip() or node_id,
        node_type=node_type,  # type: ignore[arg-type]
        name=name,
        tool=str(raw.get("tool") or raw.get("tool_name") or "").strip(),
        args=dict(raw.get("args") or raw.get("arguments") or {}) if isinstance(raw.get("args") or raw.get("arguments") or {}, dict) else {},
        rule=rule,
        prompt=str(raw.get("prompt") or "").strip(),
        children=[
            _parse_node(child, node_id=f"{node_id}.children[{index}]")
            for index, child in enumerate(children_raw)
            if isinstance(child, dict)
        ],
        success_message=str(raw.get("success_message") or "").strip(),
        failure_message=str(raw.get("failure_message") or "").strip(),
    )
    setattr(node, "require_confirmation", bool(raw.get("require_confirmation", False)))
    setattr(node, "confirmation", dict(raw.get("confirmation") or {}) if isinstance(raw.get("confirmation"), dict) else {})
    legacy_wait_seconds = int(raw.get("wait_seconds", 0) or 0)
    setattr(node, "wait_seconds", legacy_wait_seconds)
    setattr(node, "before_wait_seconds", int(raw.get("before_wait_seconds", 0) or 0))
    setattr(node, "after_wait_seconds", int(raw.get("after_wait_seconds", legacy_wait_seconds) or 0))
    setattr(node, "confirm_times", max(1, int(raw.get("confirm_times", 1) or 1)))
    setattr(node, "target_playbook_id", str(raw.get("playbook_id") or raw.get("target_playbook_id") or "").strip())
    return node


def _parse_rule_ref(raw: dict[str, Any]) -> ConditionRuleRef | None:
    assert_ref = str(raw.get("assert_ref") or "").strip()
    rule_payload = raw.get("rule")
    if isinstance(rule_payload, dict):
        rule_id = str(rule_payload.get("rule_id") or assert_ref).strip()
        inputs = dict(rule_payload.get("inputs") or {}) if isinstance(rule_payload.get("inputs"), dict) else {}
        expected = bool(rule_payload.get("expected", True))
        if rule_id:
            return ConditionRuleRef(rule_id=rule_id, inputs=inputs, expected=expected)
    if assert_ref:
        return ConditionRuleRef(rule_id=assert_ref)
    return None


def _extract_input_fields(raw_context_schema: Any) -> set[str]:
    if not isinstance(raw_context_schema, dict):
        return set()
    return {str(key).strip() for key in raw_context_schema if str(key).strip()}


def _normalize_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, list):
        return [str(item).strip() for item in raw_tags if str(item).strip()]
    return []


def _normalize_text_list(raw_items: Any) -> list[str]:
    if not isinstance(raw_items, list):
        return []
    return [str(item).strip() for item in raw_items if str(item).strip()]
