from __future__ import annotations

import posixpath
import re
import shlex
from datetime import datetime
from typing import Any

from .models import ApiError


def is_dir(st_mode: int) -> bool:
    return (st_mode & 0o170000) == 0o040000


def render_remote_command(
    template: str,
    remote_path: str,
    template_vars: dict[str, Any] | None = None,
    *,
    append_remote_path_if_missing: bool = True,
) -> str:
    normalized = template.strip()
    if not normalized:
        raise ApiError("命令模板不能为空")
    quoted_path = shlex.quote(remote_path)
    replacements: dict[str, str] = {
        "deb_path": quoted_path,
        "remote_path": quoted_path,
    }
    if template_vars:
        for key, value in template_vars.items():
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            replacements[normalized_key] = shlex.quote(str(value))

    path_placeholder_used = False
    for key, value in replacements.items():
        placeholder = f"{{{key}}}"
        if placeholder in normalized:
            normalized = normalized.replace(placeholder, value)
            if key in {"deb_path", "remote_path"} or key.endswith("_path"):
                path_placeholder_used = True

    if append_remote_path_if_missing and not path_placeholder_used:
        normalized = f"{normalized} {quoted_path}"
    return normalized


def build_backup_path(remote_path: str) -> str:
    remote_dir = posixpath.dirname(remote_path) or "/"
    file_name = posixpath.basename(remote_path)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return posixpath.join(remote_dir, f".{file_name}.bak.{timestamp}")


def short_error(result: dict[str, Any]) -> str:
    return str(result.get("stderr") or result.get("stdout") or "未知错误").strip()


CRITICAL_STDERR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r"\b[A-Za-z_]+Error:\s"),
    re.compile(r"\bException:\s"),
    re.compile(r"An error has been caught in function"),
]


def extract_critical_command_warnings(label: str, result: dict[str, Any]) -> list[str]:
    if int(result.get("exit_code", 0) or 0) != 0:
        return []
    stderr_text = str(result.get("stderr") or "")
    if not stderr_text.strip():
        return []
    for pattern in CRITICAL_STDERR_PATTERNS:
        match = pattern.search(stderr_text)
        if not match:
            continue
        snippet_start = max(match.start() - 80, 0)
        snippet_end = min(match.end() + 220, len(stderr_text))
        snippet = " ".join(stderr_text[snippet_start:snippet_end].split())
        return [f"{label}存在关键异常输出: {snippet}"]
    return []


def iter_command_output_lines(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []
    return [line.rstrip() for line in normalized.splitlines()]


def log_command_result(ctx, label: str, result: dict[str, Any]) -> None:
    ctx.log(f"{label}退出码: {result.get('exit_code', '')}")
    for stream_name, stream_label in (("stdout", "标准输出"), ("stderr", "错误输出")):
        output_lines = iter_command_output_lines(result.get(stream_name) or "")
        if not output_lines:
            continue
        ctx.log(f"{label}{stream_label}:")
        for line in output_lines:
            ctx.log(f"[{stream_name}] {line}")


def is_remote_subpath(parent_path: str, child_path: str) -> bool:
    normalized_parent = (parent_path or "/").rstrip("/") or "/"
    normalized_child = (child_path or "/").rstrip("/") or "/"
    return normalized_child == normalized_parent or normalized_child.startswith(f"{normalized_parent}/")
