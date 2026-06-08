from __future__ import annotations

from backend.playbook import PlaybookEngine


def match_playbook(playbook_engine: PlaybookEngine, content: str) -> dict[str, str | float]:
    return playbook_engine.match(content)
