from __future__ import annotations

import re

from backend.playbook.loader import load_playbooks
from backend.playbook.models import PlaybookSpec


def match_playbook(content: str) -> dict[str, str | float]:
    query = str(content or "").strip().lower()
    if not query:
        return _fallback_result()
    best_spec: PlaybookSpec | None = None
    best_score = 0.0
    for spec in load_playbooks():
        score = _score_playbook(spec, query)
        if score > best_score:
            best_spec = spec
            best_score = score
    if best_spec is None or best_score < 0.3:
        return _fallback_result()
    return {
        "id": best_spec.meta.playbook_id,
        "title": best_spec.meta.name,
        "topic": best_spec.meta.category,
        "summary": f"命中 playbook：{best_spec.meta.name}",
        "detail": _build_detail(best_spec),
        "confidence": round(min(best_score, 1.0), 3),
        "source_path": str(getattr(best_spec.meta, "source_path", "")),
    }


def _score_playbook(spec: PlaybookSpec, query: str) -> float:
    title = spec.meta.name.lower()
    score = 0.0
    if title and title in query:
        score += 0.7
    query_tokens = _tokenize(query)
    playbook_tokens = _tokenize(title)
    if query_tokens and playbook_tokens:
        overlap = len(query_tokens & playbook_tokens)
        score += overlap / max(len(query_tokens), 1)
    return score


def _tokenize(text: str) -> set[str]:
    normalized = str(text or "").strip().lower()
    parts = re.split(r"[^a-z0-9\u4e00-\u9fff]+", normalized)
    tokens = {item for item in parts if item}
    for item in list(tokens):
        if len(item) >= 2:
            tokens.add(item.replace("-", ""))
    return tokens


def _build_detail(spec: PlaybookSpec) -> str:
    details = [f"type={spec.meta.category}"]
    if spec.meta.description:
        details.append(spec.meta.description)
    return "；".join(details)


def _fallback_result() -> dict[str, str | float]:
    return {
        "id": "",
        "title": "",
        "topic": "general",
        "summary": "当前未使用固定 playbook，进入通用诊断路径",
        "detail": "当前继续走通用知识检索与工具规划路径。",
        "confidence": 0.0,
    }
