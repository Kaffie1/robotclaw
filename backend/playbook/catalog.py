from __future__ import annotations

from backend.playbook.loader import get_playbook_catalog


def list_playbook_catalog() -> list[dict[str, str]]:
    return get_playbook_catalog()
