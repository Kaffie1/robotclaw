from .schema import (
    validate_playbook_spec,
)
from .loader import find_playbook_by_id, get_playbook_catalog, load_playbooks
from .matcher import match_playbook_by_title


def build_fault_doc_context(playbook: dict | None) -> str:
    from .catalog import build_fault_doc_context_from_playbook

    return build_fault_doc_context_from_playbook(playbook)


def execute_playbook(playbook, tool_context, **kwargs):
    from ..bt.executor import execute_playbook as _execute_playbook

    return _execute_playbook(playbook, tool_context, **kwargs)


def list_playbooks(workflow_type: str | None = None):
    from .catalog import list_playbooks as _list_playbooks

    return _list_playbooks(workflow_type=workflow_type)


def build_fault_doc_context_from_playbook(playbook):
    from .catalog import build_fault_doc_context_from_playbook as _build_fault_doc_context_from_playbook

    return _build_fault_doc_context_from_playbook(playbook)


def run_scripted_playbook_by_id(playbook_id, tool_context, **kwargs):
    from .catalog import run_scripted_playbook_by_id as _run_scripted_playbook_by_id

    return _run_scripted_playbook_by_id(playbook_id, tool_context, **kwargs)


def run_scripted_fault_playbook(playbook: dict | None, tool_context, **kwargs):
    if not isinstance(playbook, dict):
        return None
    return execute_playbook(playbook, tool_context, **kwargs)


__all__ = [
    "build_fault_doc_context",
    "build_fault_doc_context_from_playbook",
    "execute_playbook",
    "find_playbook_by_id",
    "get_playbook_catalog",
    "list_playbooks",
    "load_playbooks",
    "match_playbook_by_title",
    "run_scripted_playbook_by_id",
    "run_scripted_fault_playbook",
    "validate_playbook_spec",
]
