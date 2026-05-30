from __future__ import annotations

from typing import Any


def strip_compose_warning_lines(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "level=warning" in line and "variable is not set. Defaulting to a blank string." in line:
            continue
        if "level=warning" in line and "project has been loaded without an explicit name from a symlink." in line:
            continue
        cleaned_lines.append(raw_line)
    return "\n".join(cleaned_lines).strip()


def build_command_output_text(result: dict[str, Any]) -> str:
    stdout = strip_compose_warning_lines(str(result.get("stdout") or ""))
    stderr = strip_compose_warning_lines(str(result.get("stderr") or ""))
    parts: list[str] = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n\n".join(parts).strip()
