import os
import posixpath
import pwd
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...core.config import PROJECT_ROOT_CANDIDATES, UPLOAD_CHUNK_SIZE
from ...core.models import ApiError, ConnectionConfig
from ...shared.remote import build_backup_path, short_error
from .base import RobotClient
from .ssh import IGNORED_REMOTE_ENTRY_NAMES


class LocalRobotClient(RobotClient):
    def __init__(self) -> None:
        self.home_dir = str(Path.home())

    @property
    def connected(self) -> bool:
        return True

    def connect(self, config: ConnectionConfig) -> None:
        _ = config
        self.home_dir = str(Path.home())

    def connect_via_jump(self, jump_client: Any, config: ConnectionConfig) -> None:
        _ = jump_client
        raise ApiError("本机模式不支持通过跳板连接，请直接连接目标处理器")

    def close(self) -> None:
        return

    def ensure_connected(self) -> None:
        return

    def _run_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        interactive: bool = False,
        input_text: str | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        shell_flag = "-ic" if interactive else "-lc"
        try:
            completed = subprocess.run(
                ["bash", shell_flag, str(command or "")],
                input=(str(input_text or "") + ("\n" if input_text and not str(input_text).endswith("\n") else "")) or None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApiError(f"命令执行超时（>{float(timeout or 0):.0f}s）: {command}") from exc
        stdout_text = str(completed.stdout or "").strip()
        stderr_text = str(completed.stderr or "").strip()
        if callable(output_callback):
            for line in stdout_text.splitlines():
                normalized_line = str(line or "").strip()
                if normalized_line:
                    output_callback(normalized_line)
            for line in stderr_text.splitlines():
                normalized_line = str(line or "").strip()
                if normalized_line:
                    output_callback(normalized_line)
        return {
            "exit_code": int(completed.returncode),
            "stdout": stdout_text,
            "stderr": stderr_text,
        }

    def exec_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return self._run_command(command, timeout=timeout, output_callback=output_callback)

    def exec_noninteractive_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return self._run_command(command, timeout=timeout, output_callback=output_callback)

    def exec_sudo_command(
        self,
        command: str,
        password: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        wrapped = f"sudo -S -p '' bash -lc {shlex.quote(command)}"
        return self._run_command(wrapped, timeout=timeout, input_text=password, output_callback=output_callback)

    def exec_interactive_command(
        self,
        command: str,
        *,
        timeout: float = 20.0,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return self._run_command(command, timeout=timeout, interactive=True, output_callback=output_callback)

    def get_interactive_env(self, name: str, *, timeout: float = 10.0) -> str:
        variable_name = str(name or "").strip()
        if not variable_name:
            raise ApiError("环境变量名不能为空")
        result = self.exec_interactive_command(f"printf %s \"${variable_name}\"", timeout=timeout)
        if int(result.get("exit_code", 0) or 0) != 0:
            raise ApiError(f"读取环境变量失败: {variable_name}")
        return str(result.get("stdout") or "").strip()

    def get_home_dir(self) -> str:
        return self.home_dir

    def resolve_remote_path(self, remote_path: str) -> str:
        normalized = str(remote_path or "").strip()
        if not normalized:
            return ""
        if normalized == "~":
            return self.get_home_dir()
        if normalized.startswith("~/"):
            return posixpath.join(self.get_home_dir(), normalized[2:])
        return normalized

    def ensure_remote_dir(self, remote_dir: str) -> None:
        normalized_dir = self.resolve_remote_path(remote_dir)
        if normalized_dir:
            Path(normalized_dir).mkdir(parents=True, exist_ok=True)

    def _upload_reader(self, reader, total_bytes: int, remote_path: str, progress_callback=None) -> str:
        target_path = Path(self.resolve_remote_path(remote_path))
        self.ensure_remote_dir(str(target_path.parent))
        transferred_bytes = 0
        with target_path.open("wb") as target_stream:
            while True:
                chunk = reader(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                target_stream.write(chunk)
                transferred_bytes += len(chunk)
                if progress_callback:
                    progress_callback(transferred_bytes, total_bytes)
        actual_size = int(target_path.stat().st_size)
        if actual_size != total_bytes:
            raise ApiError(f"本机上传大小异常: 预期 {total_bytes} 字节, 实际 {actual_size} 字节")
        return str(target_path)

    def upload_bytes(self, data: bytes, remote_path: str, progress_callback=None) -> str:
        total_bytes = len(data)
        view = memoryview(data)
        offset = 0

        def reader(chunk_size: int) -> bytes:
            nonlocal offset
            if offset >= total_bytes:
                return b""
            chunk = bytes(view[offset : offset + chunk_size])
            offset += len(chunk)
            return chunk

        return self._upload_reader(reader, total_bytes, remote_path, progress_callback=progress_callback)

    def upload_local_file(self, local_path: str | Path, remote_path: str, progress_callback=None) -> str:
        source_path = Path(local_path)
        try:
            source_stat = source_path.stat()
        except OSError as exc:
            raise ApiError(f"读取本地待上传文件失败: {source_path}") from exc
        with source_path.open("rb") as local_stream:
            uploaded_path = self._upload_reader(local_stream.read, int(source_stat.st_size), remote_path, progress_callback=progress_callback)
        os.chmod(uploaded_path, source_stat.st_mode & 0o777)
        return uploaded_path

    def upload_local_tree(self, local_dir: str | Path, remote_dir: str) -> list[str]:
        source_dir = Path(local_dir)
        if not source_dir.exists():
            raise ApiError(f"本地目录不存在: {source_dir}")
        if not source_dir.is_dir():
            raise ApiError(f"本地路径不是目录: {source_dir}")
        target_root = Path(self.resolve_remote_path(remote_dir))
        self.ensure_remote_dir(str(target_root))
        uploaded_paths: list[str] = []
        for path in sorted(source_dir.rglob("*")):
            relative_path = path.relative_to(source_dir).as_posix()
            target_path = target_root / relative_path
            if path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            self.upload_local_file(path, target_path.as_posix())
            uploaded_paths.append(target_path.as_posix())
        return uploaded_paths

    def list_dir(self, remote_dir: str) -> list[dict[str, Any]]:
        normalized_dir = Path(self.resolve_remote_path(remote_dir))
        entries: list[dict[str, Any]] = []
        for item in normalized_dir.iterdir():
            if item.name in IGNORED_REMOTE_ENTRY_NAMES:
                continue
            item_stat = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "path": item.as_posix(),
                    "is_dir": item.is_dir(),
                    "size": int(item_stat.st_size),
                    "mtime": int(item_stat.st_mtime),
                }
            )
        entries.sort(key=lambda entry: (not entry["is_dir"], entry["name"].lower()))
        return entries

    def read_file_bytes(self, remote_path: str) -> bytes:
        return Path(self.resolve_remote_path(remote_path)).read_bytes()

    def path_exists(self, remote_path: str, *, refresh: bool = False) -> bool:
        _ = refresh
        return Path(self.resolve_remote_path(remote_path)).exists()

    def get_remote_file_owner(self, remote_path: str) -> str:
        normalized_path = Path(self.resolve_remote_path(remote_path))
        try:
            return pwd.getpwuid(normalized_path.stat().st_uid).pw_name
        except KeyError:
            return str(normalized_path.stat().st_uid)

    def ensure_remote_executable(self, remote_path: str, *, sudo_password: str = "") -> dict[str, Any]:
        _ = sudo_password
        normalized_path = Path(self.resolve_remote_path(remote_path))
        current_mode = normalized_path.stat().st_mode
        os.chmod(normalized_path, current_mode | 0o111)
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    def is_dir_path(self, remote_path: str) -> bool:
        return Path(self.resolve_remote_path(remote_path)).is_dir()

    def backup_remote_path(self, remote_path: str, *, sudo_password: str = "") -> str | None:
        normalized_path = self.resolve_remote_path(remote_path)
        if not self.path_exists(normalized_path):
            return None
        backup_path = build_backup_path(normalized_path)
        command = f"cp -a -- {shlex.quote(normalized_path)} {shlex.quote(backup_path)}"
        result = self.exec_sudo_command(command, sudo_password) if sudo_password else self.exec_command(command)
        if result["exit_code"] != 0:
            raise ApiError(f"本机备份失败: {short_error(result)}")
        return backup_path

    def restore_backup(self, backup_path: str, remote_path: str) -> dict[str, Any]:
        normalized_backup_path = self.resolve_remote_path(backup_path)
        normalized_remote_path = self.resolve_remote_path(remote_path)
        result = self.exec_command(f"cp -a -- {shlex.quote(normalized_backup_path)} {shlex.quote(normalized_remote_path)}")
        if result["exit_code"] != 0:
            raise ApiError(f"恢复备份失败: {short_error(result)}")
        return result

    def move_remote_path(self, source_path: str, target_path: str, *, sudo_password: str = "") -> dict[str, Any]:
        normalized_source_path = self.resolve_remote_path(source_path)
        normalized_target_path = self.resolve_remote_path(target_path)
        self.ensure_remote_dir(posixpath.dirname(normalized_target_path))
        command = f"mv -f -- {shlex.quote(normalized_source_path)} {shlex.quote(normalized_target_path)}"
        result = self.exec_sudo_command(command, sudo_password) if sudo_password else self.exec_command(command)
        if result["exit_code"] != 0:
            raise ApiError(f"移动目标文件失败: {short_error(result)}")
        return result

    def remove_remote_path(self, remote_path: str, *, recursive: bool = False, sudo_password: str = "") -> dict[str, Any]:
        target_path = self.resolve_remote_path(remote_path)
        existed_before = self.path_exists(target_path)
        if not existed_before:
            return {
                "target_path": target_path,
                "recursive": recursive,
                "used_sudo": bool(sudo_password),
                "existed_before": False,
                "command": "",
                "result": {"exit_code": 0, "stdout": "", "stderr": ""},
                "exists_after": False,
                "removed": False,
            }
        command = "rm -rf --" if recursive else "rm -f --"
        raw_command = f"{command} {shlex.quote(target_path)}"
        result = self.exec_sudo_command(raw_command, sudo_password) if sudo_password else self.exec_command(raw_command)
        if result["exit_code"] != 0:
            raise ApiError(f"删除目标路径失败: {short_error(result)}")
        exists_after = self.path_exists(target_path)
        if exists_after:
            raise ApiError(f"删除命令已执行，但目标路径仍存在: {target_path}")
        return {
            "target_path": target_path,
            "recursive": recursive,
            "used_sudo": bool(sudo_password),
            "existed_before": True,
            "command": raw_command,
            "result": result,
            "exists_after": exists_after,
            "removed": True,
        }

    def remove_files_by_prefix(self, remote_dir: str, prefix: str, *, sudo_password: str = "") -> list[str]:
        _ = sudo_password
        target_dir = Path(self.resolve_remote_path(remote_dir))
        if not target_dir.exists():
            return []
        normalized_prefix = str(prefix or "").strip()
        if not normalized_prefix:
            raise ApiError("prefix 不能为空")
        removed_files: list[str] = []
        for item in target_dir.iterdir():
            if item.is_file() and item.name.startswith(normalized_prefix):
                item.unlink()
                removed_files.append(item.as_posix())
        return removed_files

    def walk_entries(self, root_path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        root = Path(self.resolve_remote_path(root_path))
        for current_root, dir_names, file_names in os.walk(root):
            current_path = Path(current_root)
            for dir_name in dir_names:
                path = current_path / dir_name
                path_stat = path.stat()
                results.append(
                    {
                        "name": dir_name,
                        "path": path.as_posix(),
                        "is_dir": True,
                        "size": int(path_stat.st_size),
                        "mtime": int(path_stat.st_mtime),
                    }
                )
            for file_name in file_names:
                if file_name in IGNORED_REMOTE_ENTRY_NAMES:
                    continue
                path = current_path / file_name
                path_stat = path.stat()
                results.append(
                    {
                        "name": file_name,
                        "path": path.as_posix(),
                        "is_dir": False,
                        "size": int(path_stat.st_size),
                        "mtime": int(path_stat.st_mtime),
                    }
                )
        return results

    def list_files_recursive(self, root_path: str, *, require_birth_time: bool = False) -> list[dict[str, Any]]:
        resolved_root = Path(self.resolve_remote_path(root_path))
        entries: list[dict[str, Any]] = []
        for path in sorted(resolved_root.rglob("*")):
            if not path.is_file() or path.name in IGNORED_REMOTE_ENTRY_NAMES:
                continue
            path_stat = path.stat()
            birth_time = int(getattr(path_stat, "st_birthtime", 0) or 0)
            if require_birth_time and birth_time <= 0:
                raise ApiError(f"文件系统不支持按创建时间筛选，缺少 birth time: {path.as_posix()}")
            entries.append(
                {
                    "name": path.name,
                    "path": path.as_posix(),
                    "relative_path": path.relative_to(resolved_root).as_posix(),
                    "is_dir": False,
                    "size": int(path_stat.st_size),
                    "mtime": int(path_stat.st_mtime),
                    "ctime": int(path_stat.st_ctime),
                    "birth_time": birth_time,
                    "created_at": birth_time,
                }
            )
        return entries

    def directory_shortcuts(self) -> dict[str, Any]:
        home_dir = self.get_home_dir()
        shortcuts: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        preferred_root = ""
        for candidate_path, label in PROJECT_ROOT_CANDIDATES:
            resolved_path = self.resolve_remote_path(candidate_path)
            if resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            exists = self.path_exists(resolved_path)
            if exists and not preferred_root:
                preferred_root = resolved_path
            shortcuts.append(
                {
                    "label": label,
                    "path": resolved_path,
                    "display_path": candidate_path,
                    "exists": exists,
                }
            )
        for shortcut in [
            {"label": "机器人 Home", "path": home_dir, "display_path": "~", "exists": True},
            {"label": "临时目录 /tmp", "path": "/tmp", "display_path": "/tmp", "exists": self.path_exists("/tmp")},
            {"label": "根目录 /", "path": "/", "display_path": "/", "exists": True},
        ]:
            if shortcut["path"] in seen_paths:
                continue
            seen_paths.add(shortcut["path"])
            shortcuts.append(shortcut)
        if not preferred_root:
            preferred_root = home_dir
        return {"shortcuts": shortcuts, "preferred_root": preferred_root}
