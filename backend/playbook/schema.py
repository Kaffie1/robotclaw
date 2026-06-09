from __future__ import annotations

from backend.playbook.models import BTNodeSpec, PlaybookSpec


def validate_playbook_spec(spec: PlaybookSpec) -> None:
    if not spec.meta.playbook_id.strip():
        raise ValueError("playbook_id is required")
    if not spec.meta.name.strip():
        raise ValueError("playbook name is required")
    _validate_node(spec.root)


def _validate_node(node: BTNodeSpec) -> None:
    if not node.node_id.strip():
        raise ValueError("node_id is required")
    if not node.name.strip():
        raise ValueError("node name is required")
    if node.node_type in {"sequence", "selector"} and not node.children:
        raise ValueError(f"{node.node_type} node requires children: {node.node_id}")
    if node.node_type == "condition" and node.rule is None:
        raise ValueError(f"condition node requires rule: {node.node_id}")
    if node.node_type == "call_playbook" and not str(getattr(node, "target_playbook_id", "")).strip():
        raise ValueError(f"call_playbook node requires target_playbook_id: {node.node_id}")
    for child in node.children:
        _validate_node(child)
