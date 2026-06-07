from __future__ import annotations

from ..state import FaultRouteState
from ....core.shared import append_fault_trace
from ....runtime.playbooks.loader import get_playbook_catalog
from ..timing import log_stage_duration, start_stage_timer


def load_catalog_node(_: FaultRouteState) -> FaultRouteState:
    started_at = start_stage_timer()
    playbooks = get_playbook_catalog(workflow_type=None)
    append_fault_trace(
        "route_catalog_loaded",
        {
            "count": len(playbooks),
            "playbooks": playbooks,
        },
    )
    log_stage_duration("load_catalog", started_at, count=len(playbooks))
    return {"playbooks": playbooks}


__all__ = ["load_catalog_node"]
