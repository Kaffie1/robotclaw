from __future__ import annotations

from ..state import FaultRouteState
from ....core.shared import append_fault_trace
from ....runtime.playbooks.loader import get_playbook_catalog


def load_catalog_node(_: FaultRouteState) -> FaultRouteState:
    playbooks = get_playbook_catalog(workflow_type="fault")
    append_fault_trace(
        "route_catalog_loaded",
        {
            "count": len(playbooks),
            "playbooks": playbooks,
        },
    )
    return {"playbooks": playbooks}


__all__ = ["load_catalog_node"]
