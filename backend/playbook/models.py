from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlaybookExecutionState:
    playbook_id: str = ""
    current_node: str = ""
    status: str = "idle"
    variables: dict[str, Any] = field(default_factory=dict)
