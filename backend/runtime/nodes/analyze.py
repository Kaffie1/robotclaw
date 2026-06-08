from __future__ import annotations

from backend.playbook import PlaybookEngine


def analyze_problem(
    playbook_engine: PlaybookEngine,
    playbook_id: str,
    tool_results: list[dict],
    connected: bool,
) -> dict[str, str]:
    return playbook_engine.analyze(playbook_id, tool_results, connected)
