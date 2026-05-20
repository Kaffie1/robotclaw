import os
import posixpath
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from fastapi import Request, UploadFile

from ..core.config import (
    CHFS_HOST,
    CHFS_PASSWORD,
    CHFS_PORT,
    CHFS_USER,
    CONNECTION_CACHE_PATH,
    DATA_DIR,
    DB_PATH,
    DOWNLOAD_TMP_DIR,
    LEGACY_CONNECTION_CACHE_PATH,
    LEGACY_DB_PATH,
    MODULE_DEPLOY_NAMES,
    STATIC_DIR,
    TEMPLATE_DIR,
)
from ..core.models import ApiError
from .validation import require_text, require_upload


def is_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def get_asset_version() -> str:
    candidates = [TEMPLATE_DIR / "index.html", *sorted((STATIC_DIR / "css").glob("*.css")), *sorted((STATIC_DIR / "js").glob("*.js"))]
    latest_mtime = 0.0
    for path in candidates:
        try:
            latest_mtime = max(latest_mtime, path.stat().st_mtime)
        except OSError:
            continue
    return str(int(latest_mtime))


def migrate_legacy_runtime_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    migrations = [
        (LEGACY_DB_PATH, DB_PATH),
        (LEGACY_CONNECTION_CACHE_PATH, CONNECTION_CACHE_PATH),
    ]
    for legacy_path, target_path in migrations:
        if legacy_path == target_path:
            continue
        if not legacy_path.exists() or target_path.exists():
            continue
        legacy_path.replace(target_path)


def extract_package_prefix(file_name: str) -> str:
    normalized = os.path.basename(require_text(file_name, "文件名不能为空"))
    prefix = normalized.split("_", 1)[0].strip()
    if not prefix:
        raise ApiError(f"无法从文件名解析模块前缀: {normalized}")
    return prefix


def resolve_module_path(module_name: str) -> str:
    normalized = require_text(module_name, "请选择要部署的模块")
    if normalized not in MODULE_DEPLOY_NAMES:
        raise ApiError(f"不支持的模块: {normalized}")
    return posixpath.join("/home/naviai/navi_project/.dists", normalized)


def resolve_download_source_path(raw_path: Any) -> str:
    """从输入内容中解析出可下载的文件服务器路径，支持直接输入路径或完整 URL"""
    text = require_text(raw_path, "文件服务器包路径不能为空").replace("\\", "/").strip()
    parsed = urllib.parse.urlparse(text)
    candidate = parsed.path if parsed.scheme else text
    slash_index = candidate.find("/")
    if slash_index >= 0:
        candidate = candidate[slash_index:]
    candidate = candidate.strip()
    if not candidate:
        raise ApiError("无法从输入内容中裁剪出可下载路径")
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    return urllib.parse.unquote(candidate)


def download_file_from_chfs(remote_file: str, local_file: Path) -> Path:
    """从 CHFS 文件服务器下载文件到本地临时路径，返回本地文件路径"""
    local_file.parent.mkdir(parents=True, exist_ok=True)
    base_url = f"http://{CHFS_HOST}:{CHFS_PORT}"
    session = requests.Session()
    try:
        login_url = f"{base_url.rstrip('/')}/chfs/session"
        login_response = session.post(login_url, data={"user": CHFS_USER, "pwd": CHFS_PASSWORD}, timeout=30)
        login_response.raise_for_status()

        attempts = [
            (f"{base_url.rstrip('/')}/chfs/download", {"filepath": remote_file}),
            (f"{base_url.rstrip('/')}{remote_file}", None),
        ]
        last_error: Exception | None = None
        for url, params in attempts:
            try:
                with session.get(url, params=params, timeout=300, stream=True) as response:
                    response.raise_for_status()
                    with local_file.open("wb") as file_obj:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                file_obj.write(chunk)
                    return local_file
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ApiError(f"下载失败: {remote_file}")
    finally:
        try:
            session.delete(f"{base_url}/chfs/session", timeout=10)
        except Exception:  # noqa: BLE001
            pass


def prepare_package_bytes(upload: UploadFile | None, server_file_path: str, *, local_error_message: str) -> tuple[str, bytes, dict[str, Any]]:
    """准备部署安装包的字节内容，优先使用上传文件，其次使用服务器文件路径"""
    source_path = str(server_file_path or "").strip()
    if source_path:
        remote_file = resolve_download_source_path(source_path)
        file_name = os.path.basename(remote_file)
        if not file_name:
            raise ApiError(f"无法从文件服务器路径解析文件名: {remote_file}")
        local_file = DOWNLOAD_TMP_DIR / file_name
        download_file_from_chfs(remote_file, local_file)
        return file_name, local_file.read_bytes(), {
            "source_kind": "file_server",
            "source_path": source_path,
            "download_path": remote_file,
            "local_tmp_path": str(local_file),
        }

    resolved_upload = require_upload(upload, local_error_message)
    file_name = os.path.basename(resolved_upload.filename or "")
    return file_name, resolved_upload.file.read(), {
        "source_kind": "local_upload",
        "source_path": "",
        "download_path": "",
        "local_tmp_path": "",
    }


def prepare_package_source(upload: UploadFile | None, server_file_path: str, *, local_error_message: str) -> tuple[str, dict[str, Any]]:
    """准备部署安装包来源信息，本地上传会先落盘，文件服务器路径仅记录来源，实际下载延后到任务执行阶段。"""
    source_path = str(server_file_path or "").strip()
    if source_path:
        remote_file = resolve_download_source_path(source_path)
        file_name = os.path.basename(remote_file)
        if not file_name:
            raise ApiError(f"无法从文件服务器路径解析文件名: {remote_file}")
        return file_name, {
            "source_kind": "file_server",
            "source_path": source_path,
            "download_path": remote_file,
            "local_tmp_path": "",
            "source_file_name": file_name,
        }

    resolved_upload = require_upload(upload, local_error_message)
    file_name = os.path.basename(resolved_upload.filename or "")
    if not file_name:
        raise ApiError("无法从上传文件解析文件名")
    DOWNLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"-{file_name}"
    with tempfile.NamedTemporaryFile(delete=False, dir=DOWNLOAD_TMP_DIR, prefix="package-upload-", suffix=suffix) as file_obj:
        file_obj.write(resolved_upload.file.read())
        local_tmp_path = file_obj.name
    return file_name, {
        "source_kind": "local_upload",
        "source_path": "",
        "download_path": "",
        "local_tmp_path": local_tmp_path,
        "source_file_name": file_name,
    }


def materialize_package_bytes_from_source(source_metadata: dict[str, Any], *, local_error_message: str) -> tuple[str, bytes, dict[str, Any]]:
    """根据来源信息读取部署安装包字节内容，必要时从文件服务器下载到本地临时目录。"""
    source_kind = str(source_metadata.get("source_kind") or "").strip()
    file_name = os.path.basename(str(source_metadata.get("source_file_name") or "").strip())
    if source_kind == "file_server":
        remote_file = resolve_download_source_path(source_metadata.get("source_path") or source_metadata.get("download_path") or "")
        file_name = file_name or os.path.basename(remote_file)
        if not file_name:
            raise ApiError(f"无法从文件服务器路径解析文件名: {remote_file}")
        local_file = DOWNLOAD_TMP_DIR / file_name
        download_file_from_chfs(remote_file, local_file)
        normalized_metadata = {
            "source_kind": "file_server",
            "source_path": str(source_metadata.get("source_path") or ""),
            "download_path": remote_file,
            "local_tmp_path": str(local_file),
            "source_file_name": file_name,
        }
        return file_name, local_file.read_bytes(), normalized_metadata

    local_tmp_path = str(source_metadata.get("local_tmp_path") or "").strip()
    if not local_tmp_path:
        raise ApiError(local_error_message)
    local_file = Path(local_tmp_path)
    if not local_file.exists():
        raise ApiError(f"本地临时安装包不存在: {local_tmp_path}")
    file_name = file_name or os.path.basename(local_tmp_path)
    normalized_metadata = {
        "source_kind": "local_upload",
        "source_path": "",
        "download_path": "",
        "local_tmp_path": local_tmp_path,
        "source_file_name": file_name,
    }
    return file_name, local_file.read_bytes(), normalized_metadata
