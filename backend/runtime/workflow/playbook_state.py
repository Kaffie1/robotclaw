from __future__ import annotations


def build_playbook_state_payload(playbook_id: str, current_node_id: str, status: str) -> dict[str, str]:
    return {
        "playbook_id": playbook_id,
        "current_node_id": current_node_id,
        "status": status,
    }
