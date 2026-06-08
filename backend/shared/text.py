from __future__ import annotations


def infer_title(content: str, default: str) -> str:
    text = " ".join(content.split()).strip()
    if not text:
        return default
    return text[:18] + ("..." if len(text) > 18 else "")
