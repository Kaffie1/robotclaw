from __future__ import annotations

import re


ATTACHMENT_SUMMARY_PATTERN = re.compile(r"\s*\[\d+\s*张图片\]\s*")


def infer_title(content: str, default: str) -> str:
    text = " ".join(content.split()).strip()
    if not text:
        return default
    return text[:18] + ("..." if len(text) > 18 else "")


def strip_image_attachment_summary(content: str) -> str:
    text = ATTACHMENT_SUMMARY_PATTERN.sub(" ", str(content or "")).strip()
    return "" if text == "图片" else text
