import json
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from ..core.models import ApiError


def require_text(value: Any, message: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApiError(message)
    return text


def parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_json_config(path: Path, default_payload: Any, *, label: str = "配置") -> Any:
    if not path.exists():
        return json.loads(json.dumps(default_payload, ensure_ascii=False))
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except json.JSONDecodeError as exc:
        raise ApiError(f"{label}格式错误: {exc}") from exc
    except OSError as exc:
        raise ApiError(f"读取{label}失败: {exc}") from exc


def require_upload(upload: UploadFile | None, message: str) -> UploadFile:
    """验证上传文件是否存在且具有有效的文件名，返回 UploadFile 对象供后续处理"""
    if upload is None or not str(upload.filename or "").strip():
        raise ApiError(message)
    return upload
