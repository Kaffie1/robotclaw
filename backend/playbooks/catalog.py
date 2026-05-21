from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml

from .executor import execute_playbook
from .loader import find_playbook_by_id, get_playbook_catalog, load_playbooks


def list_playbooks(workflow_type: str | None = None) -> list[dict[str, Any]]:
    return load_playbooks(workflow_type=workflow_type)


def build_fault_doc_context_from_playbook(playbook: dict[str, Any] | None) -> str:
    if not isinstance(playbook, dict):
        return ""
    summary = {
        "id": playbook.get("id", ""),
        "title": playbook.get("title", ""),
        "source_path": playbook.get("source_path", ""),
        "rules_source_path": playbook.get("rules_source_path", ""),
        "root": playbook.get("root", {}),
        "escalation_notes": playbook.get("escalation_notes", []),
        "execution_notes": playbook.get("execution_notes", []),
    }
    return "相关 playbook：\n" + yaml.safe_dump(summary, allow_unicode=True, sort_keys=False).strip()


def run_scripted_playbook_by_id(
    playbook_id: str,
    tool_context: dict[str, Any] | None,
    *,
    workflow_type: str | None = None,
    resume_state: dict[str, Any] | None = None,
    status_reporter: Callable[[dict[str, Any]], None] | None = None,
    tree_status_reporter: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    matched = find_playbook_by_id(playbook_id, workflow_type=workflow_type)
    if not matched:
        return None
    return execute_playbook(
        matched,
        tool_context,
        resume_state=resume_state,
        status_reporter=status_reporter,
        tree_status_reporter=tree_status_reporter,
    )
