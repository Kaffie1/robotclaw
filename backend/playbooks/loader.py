from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..core.config import FAULT_PLAYBOOKS_PATH, NORMAL_WORKFLOWS_PATH


ALLOWED_WORKFLOW_TYPES = {"fault", "normal"}


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _normalize_workflow_type(workflow_type: str | None) -> str:
    normalized = str(workflow_type or "").strip().lower()
    if normalized not in ALLOWED_WORKFLOW_TYPES:
        return ""
    return normalized


def _iter_workflow_roots(workflow_type: str | None) -> list[tuple[str, Path]]:
    normalized = _normalize_workflow_type(workflow_type)
    if normalized == "fault":
        return [("fault", Path(FAULT_PLAYBOOKS_PATH))]
    if normalized == "normal":
        return [("normal", Path(NORMAL_WORKFLOWS_PATH))]
    return [
        ("fault", Path(FAULT_PLAYBOOKS_PATH)),
        ("normal", Path(NORMAL_WORKFLOWS_PATH)),
    ]


def load_playbooks(workflow_type: str | None = None) -> list[dict[str, Any]]:
    playbooks: list[dict[str, Any]] = []
    for default_workflow_type, playbooks_root in _iter_workflow_roots(workflow_type):
        if playbooks_root.is_file():
            playbook_files = [playbooks_root]
        elif playbooks_root.is_dir():
            playbook_files = sorted(playbooks_root.rglob("playbook.yaml"))
        else:
            continue
        for playbook_file in playbook_files:
            playbooks.extend(_load_playbooks_from_file(playbook_file, default_workflow_type=default_workflow_type))
    return playbooks


def _load_playbooks_from_file(playbook_file: Path, *, default_workflow_type: str) -> list[dict[str, Any]]:
    playbooks: list[dict[str, Any]] = []
    playbook_text = read_text_file(playbook_file)
    if not playbook_text:
        return playbooks
    try:
        payload = yaml.safe_load(playbook_text)
    except Exception:  # noqa: BLE001
        return playbooks
    if not isinstance(payload, dict):
        return playbooks
    if isinstance(payload.get("playbooks"), list):
        for item in payload.get("playbooks") or []:
            if isinstance(item, dict):
                playbook = dict(item)
                normalized_type = _normalize_workflow_type(playbook.get("type") or playbook.get("workflow_type")) or default_workflow_type
                playbook["type"] = normalized_type
                playbook["workflow_type"] = normalized_type
                playbook.setdefault("source_path", str(playbook_file))
                playbook.setdefault("rules_source_path", str(playbook_file.with_name("rules.yaml")))
                playbooks.append(playbook)
        return playbooks
    normalized_type = _normalize_workflow_type(payload.get("type") or payload.get("workflow_type")) or default_workflow_type
    payload["type"] = normalized_type
    payload["workflow_type"] = normalized_type
    payload.setdefault("source_path", str(playbook_file))
    payload.setdefault("rules_source_path", str(playbook_file.with_name("rules.yaml")))
    playbooks.append(payload)
    return playbooks


def find_playbook_by_id(playbook_id: str, workflow_type: str | None = None) -> dict[str, Any] | None:
    normalized_id = str(playbook_id or "").strip()
    if not normalized_id:
        return None
    for playbook in load_playbooks(workflow_type=workflow_type):
        if str(playbook.get("id") or "").strip() == normalized_id:
            return playbook
    return None


def get_playbook_catalog(workflow_type: str | None = None) -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    for playbook in load_playbooks(workflow_type=workflow_type):
        catalog.append(
            {
                "id": str(playbook.get("id") or "").strip(),
                "title": str(playbook.get("title") or "").strip(),
                "type": str(playbook.get("type") or playbook.get("workflow_type") or "").strip().lower(),
            }
        )
    return [item for item in catalog if item["id"] and item["title"]]
