import posixpath
import re
import shlex
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import paramiko

from ..core.config import PROJECT_ROOT_CANDIDATES, UPLOAD_CHUNK_SIZE
from ..shared.remote import build_backup_path, is_dir, iter_command_output_lines, short_error
from ..core.models import ApiError, ConnectionConfig


ansi_escape_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
terminal_control_pattern = re.compile(r"[\x00-\x08\x0B-\x1A\x1C-\x1F\x7F]")
IGNORED_REMOTE_ENTRY_NAMES = {".env"}


def strip_terminal_control_sequences(text: str) -> str:
    """去除文本中的 ANSI 转义序列和其他不可见控制字符，返回清理后的文本。
        适用于清理远程命令输出中的格式化和控制字符，确保结果更易读和处理。"""
    normalized_text = str(text or "")
    normalized_text = ansi_escape_pattern.sub("", normalized_text)
    normalized_text = terminal_control_pattern.sub("", normalized_text)
    return normalized_text


class RobotClient:
    def __init__(self) -> None:
        self.ssh: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None
        self.lock = threading.RLock()
        self.home_dir = ""

    @property
    def connected(self) -> bool:
        return self.ssh is not None and self.sftp is not None

    def connect(self, config: ConnectionConfig) -> None:
        """建立 SSH 连接并初始化 SFTP 客户端，获取远程主机的 home 目录。"""
        with self.lock:
            self.close()
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs: dict[str, Any] = {
                "hostname": config.host,
                "port": config.port,
                "username": config.username,
                "timeout": config.timeout,
                "password": config.password,
                "allow_agent": False,
                "look_for_keys": False,
            }
            try:
                ssh.connect(**connect_kwargs)
                sftp = ssh.open_sftp()
                home_dir = sftp.normalize(".")
            except paramiko.AuthenticationException as exc:
                ssh.close()
                raise ApiError("SSH 认证失败，请检查用户名或密码") from exc
            except paramiko.BadHostKeyException as exc:
                ssh.close()
                raise ApiError("SSH 主机指纹校验失败") from exc
            except paramiko.SSHException as exc:
                ssh.close()
                raise ApiError(f"SSH 连接失败: {exc}") from exc
            except OSError as exc:
                ssh.close()
                raise ApiError(f"无法连接到主机 {config.host}:{config.port}: {exc}") from exc
            self.ssh = ssh
            self.sftp = sftp
            self.home_dir = home_dir

    def connect_via_jump(self, jump_client: "RobotClient", config: ConnectionConfig) -> None:
        """通过跳板连接目标处理器，建立 SSH 连接并初始化 SFTP 客户端，获取远程主机的 home 目录。"""
        with self.lock:
            self.close()
            jump_client.ensure_connected()
            assert jump_client.ssh is not None
            transport = jump_client.ssh.get_transport()
            if transport is None or not transport.is_active():
                raise ApiError("跳板连接不可用，无法连接目标处理器")
            try:
                channel = transport.open_channel(
                    "direct-tcpip",
                    (config.host, int(config.port)),
                    ("127.0.0.1", 0),
                )
            except Exception as exc:  # noqa: BLE001
                raise ApiError(f"无法通过跳板连接目标处理器 {config.host}:{config.port}: {exc}") from exc

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs: dict[str, Any] = {
                "hostname": config.host,
                "port": config.port,
                "username": config.username,
                "timeout": config.timeout,
                "password": config.password,
                "allow_agent": False,
                "look_for_keys": False,
                "sock": channel,
            }
            try:
                ssh.connect(**connect_kwargs)
                sftp = ssh.open_sftp()
                home_dir = sftp.normalize(".")
            except paramiko.AuthenticationException as exc:
                ssh.close()
                raise ApiError("目标处理器 SSH 认证失败，请检查用户名或密码") from exc
            except paramiko.BadHostKeyException as exc:
                ssh.close()
                raise ApiError("目标处理器主机指纹校验失败") from exc
            except paramiko.SSHException as exc:
                ssh.close()
                raise ApiError(f"目标处理器 SSH 连接失败: {exc}") from exc
            except OSError as exc:
                ssh.close()
                raise ApiError(f"无法连接到目标处理器 {config.host}:{config.port}: {exc}") from exc
            self.ssh = ssh
            self.sftp = sftp
            self.home_dir = home_dir

    def close(self) -> None:
        """关闭 SSH 和 SFTP 连接，重置 home 目录。"""
        with self.lock:
            if self.sftp is not None:
                self.sftp.close()
                self.sftp = None
            if self.ssh is not None:
                self.ssh.close()
                self.ssh = None
            self.home_dir = ""

    def ensure_connected(self) -> None:
        """确保当前已连接到远程主机，否则抛出异常提示先连接机器人。"""
        if not self.connected:
            raise ApiError("请先连接机器人")

    def get_sftp(self, *, refresh: bool = False) -> paramiko.SFTPClient:
        """获取当前的 SFTP 客户端，如果 refresh=True 则强制刷新连接。确保在调用前已连接机器人，否则抛出异常提示先连接机器人。"""
        with self.lock:
            self.ensure_connected()
            assert self.ssh is not None
            if self.sftp is not None:
                try:
                    channel = self.sftp.get_channel()
                    if refresh or channel.closed or not channel.active:
                        self.sftp.close()
                        self.sftp = None
                except Exception:  # noqa: BLE001
                    try:
                        self.sftp.close()
                    except Exception:  # noqa: BLE001
                        pass
                    self.sftp = None
            if self.sftp is None:
                self.sftp = self.ssh.open_sftp()
                if not self.home_dir:
                    self.home_dir = self.sftp.normalize(".")
            return self.sftp

    def _exec_shell_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        input_text: str | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """执行交互式 shell 命令，返回包含 exit_code、stdout、stderr 的结果字典。
            通过特殊标记识别命令结束，确保输出完整且不受命令本身输出干扰。
            适用于需要交互式环境的命令执行，如获取环境变量、执行容器命令等。"""
        with self.lock:
            self.ensure_connected()
            assert self.ssh is not None
            channel = self.ssh.invoke_shell(width=160, height=48)
            channel.settimeout(0.2)
            marker = f"__CODEx_DONE_{uuid.uuid4().hex}__"
            marker_pattern = re.compile(rf"{re.escape(marker)}:(\d+)")
            output_chunks: list[str] = []
            emitted_lines: list[str] = []

            def drain_channel(idle_seconds: float) -> str:
                deadline = time.monotonic() + idle_seconds
                buffer: list[str] = []
                while time.monotonic() < deadline:
                    if channel.recv_ready():
                        chunk = channel.recv(4096).decode("utf-8", errors="replace")
                        if not chunk:
                            break
                        buffer.append(chunk)
                        deadline = time.monotonic() + idle_seconds
                        continue
                    time.sleep(0.05)
                return "".join(buffer)

            try:
                drain_channel(0.4)
                channel.send("stty -echo >/dev/null 2>&1 || true\n")
                channel.send("export PS1='' PS2=''; unset PROMPT_COMMAND\n")
                drain_channel(0.2)
                payload_lines = [str(command or "").rstrip()]
                normalized_input_text = str(input_text or "").rstrip("\n")
                if normalized_input_text:
                    payload_lines.append(normalized_input_text)
                payload_lines.append(f"printf '\\n{marker}:%s\\n' $?")
                channel.send("\n".join(payload_lines) + "\n")
                deadline = time.monotonic() + timeout if timeout is not None else None
                while True:
                    chunk = drain_channel(0.3)
                    if chunk:
                        output_chunks.append(chunk)
                        if callable(output_callback):
                            cleaned_live_output = strip_terminal_control_sequences("".join(output_chunks))
                            live_lines = iter_command_output_lines(cleaned_live_output)
                            if len(live_lines) > len(emitted_lines):
                                for line in live_lines[len(emitted_lines):]:
                                    normalized_line = str(line or "").strip()
                                    if normalized_line:
                                        output_callback(normalized_line)
                                emitted_lines = live_lines
                        combined_output = "".join(output_chunks)
                        marker_match = marker_pattern.search(combined_output)
                        if marker_match:
                            exit_code = int(marker_match.group(1))
                            cleaned_output = marker_pattern.sub("", combined_output)
                            cleaned_output = strip_terminal_control_sequences(cleaned_output)
                            cleaned_output = cleaned_output.strip()
                            return {
                                "exit_code": exit_code,
                                "stdout": cleaned_output,
                                "stderr": "",
                            }
                    if deadline is not None and time.monotonic() >= deadline:
                        raise ApiError(f"交互式命令执行超时（>{float(timeout):.0f}s）: {command}")
                    time.sleep(0.05)
            finally:
                channel.close()

    def _exec_noninteractive_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """执行真正的非交互 SSH 命令，避免依赖 invoke_shell + marker 收口。"""
        with self.lock:
            self.ensure_connected()
            assert self.ssh is not None
            stdin, stdout, stderr = self.ssh.exec_command(command, timeout=timeout)
            channel = stdout.channel
            channel.settimeout(0.2)
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []
            emitted_lines: list[str] = []

            def emit_live_lines() -> None:
                if not callable(output_callback):
                    return
                merged_output = "".join(stdout_chunks + stderr_chunks)
                cleaned_live_output = strip_terminal_control_sequences(merged_output)
                live_lines = iter_command_output_lines(cleaned_live_output)
                if len(live_lines) <= len(emitted_lines):
                    return
                for line in live_lines[len(emitted_lines):]:
                    normalized_line = str(line or "").strip()
                    if normalized_line:
                        output_callback(normalized_line)
                emitted_lines[:] = live_lines

            deadline = time.monotonic() + timeout if timeout is not None else None
            try:
                while True:
                    drained = False
                    while channel.recv_ready():
                        chunk = channel.recv(4096).decode("utf-8", errors="replace")
                        if not chunk:
                            break
                        stdout_chunks.append(chunk)
                        drained = True
                    while channel.recv_stderr_ready():
                        chunk = channel.recv_stderr(4096).decode("utf-8", errors="replace")
                        if not chunk:
                            break
                        stderr_chunks.append(chunk)
                        drained = True
                    if drained:
                        emit_live_lines()
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        exit_code = int(channel.recv_exit_status())
                        stdout_text = strip_terminal_control_sequences("".join(stdout_chunks)).strip()
                        stderr_text = strip_terminal_control_sequences("".join(stderr_chunks)).strip()
                        return {
                            "exit_code": exit_code,
                            "stdout": stdout_text,
                            "stderr": stderr_text,
                        }
                    if deadline is not None and time.monotonic() >= deadline:
                        stdout_tail = strip_terminal_control_sequences("".join(stdout_chunks))[-500:]
                        stderr_tail = strip_terminal_control_sequences("".join(stderr_chunks))[-500:]
                        raise ApiError(
                            f"非交互命令执行超时（>{float(timeout):.0f}s）: {command}\n"
                            f"stdout_tail={stdout_tail}\n"
                            f"stderr_tail={stderr_tail}"
                        )
                    time.sleep(0.05)
            finally:
                try:
                    stdin.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    stdout.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    stderr.close()
                except Exception:  # noqa: BLE001
                    pass

    def exec_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """执行普通 shell 命令，返回包含 exit_code、stdout、stderr 的结果字典。
            适用于不需要交互式环境的简单命令执行。"""
        return self._exec_noninteractive_command(command, timeout=timeout, output_callback=output_callback)

    def exec_noninteractive_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """显式执行非交互 SSH 命令。
            供部署、安装、健康检查等必须避免伪终端干扰的流程使用。"""
        return self._exec_noninteractive_command(command, timeout=timeout, output_callback=output_callback)

    def exec_sudo_command(
        self,
        command: str,
        password: str,
        *,
        timeout: float | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """执行需要 sudo 权限的 shell 命令，返回包含 exit_code、stdout、stderr 的结果字典。
            通过交互式方式输入密码，确保兼容各种 sudo 配置和提示。"""
        wrapped = f"sudo -S -p '' bash -lc {shlex.quote(command)}"
        return self._exec_shell_command(wrapped, timeout=timeout, input_text=password, output_callback=output_callback)

    def exec_interactive_command(
        self,
        command: str,
        *,
        timeout: float = 20.0,
        output_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """执行需要交互式环境的 shell 命令，返回包含 exit_code、stdout、stderr 的结果字典。
            适用于需要登录 shell 环境的命令执行，如获取环境变量、执行容器命令等。"""
        return self._exec_shell_command(command, timeout=timeout, output_callback=output_callback)

    def get_interactive_env(self, name: str, *, timeout: float = 10.0) -> str:
        """获取远程主机登录 shell 环境变量的值，确保通过交互式命令执行以正确加载环境。
            参数 name 是要获取的环境变量名，返回对应的值。如果环境变量不存在或读取失败，则抛出异常提示错误原因。"""
        variable_name = str(name or "").strip()
        if not variable_name:
            raise ApiError("环境变量名不能为空")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable_name):
            raise ApiError(f"非法环境变量名: {variable_name}")
        # 读取交互式 shell 环境变量，确保和容器/登录 shell 的实际行为一致。
        result = self.exec_interactive_command(f"bash -ic 'printf %s \"${variable_name}\"'", timeout=timeout)
        if int(result.get("exit_code", 0) or 0) != 0:
            raise ApiError(f"读取环境变量失败: {variable_name}")
        return str(result.get("stdout") or "").strip()

    def get_home_dir(self) -> str:
        """获取远程主机的 home 目录，使用 SFTP 客户端的 normalize 方法解析 ~，确保兼容各种用户配置和环境。
            获取后会缓存结果，后续调用会直接返回缓存值，避免重复解析和潜在的性能问题。
            如果缓存值不可用或无效，则会重新解析并更新"""
        with self.lock:
            self.ensure_connected()
            if not self.home_dir:
                self.home_dir = self.get_sftp().normalize(".")
            return self.home_dir

    def resolve_remote_path(self, remote_path: str) -> str:
        """解析远程路径，支持 ~ 和相对路径，确保返回绝对路径。
            使用 get_home_dir 方法获取 home 目录，确保兼容各种用户配置和环境。"""
        normalized = str(remote_path or "").strip()
        if not normalized:
            return ""
        if normalized == "~":
            return self.get_home_dir()
        if normalized.startswith("~/"):
            return posixpath.join(self.get_home_dir(), normalized[2:])
        return normalized

    def ensure_remote_dir(self, remote_dir: str) -> None:
        """确保远程目录存在，如果不存在则创建。支持递归创建多级目录，确保最终目录可用。
             使用 resolve_remote_path 解析路径，确保兼容 ~ 和相对路径。"""
        if not remote_dir:
            return
        with self.lock:
            self.ensure_connected()
            sftp = self.get_sftp()
            remote_dir = self.resolve_remote_path(remote_dir)
            current = "/"
            for part in [piece for piece in remote_dir.split("/") if piece]:
                current = posixpath.join(current, part)
                try:
                    sftp.stat(current)
                except FileNotFoundError:
                    sftp.mkdir(current)

    def _upload_reader(self, reader, total_bytes: int, remote_path: str, progress_callback=None) -> str:
        """使用 reader 函数读取数据并上传到远程路径，reader 函数接受一个 chunk_size 参数，返回对应大小的字节数据。"""
        with self.lock:
            self.ensure_connected()
            remote_path = self.resolve_remote_path(remote_path)
            sftp = self.get_sftp(refresh=True)
            self.ensure_remote_dir(posixpath.dirname(remote_path))
            transferred_bytes = 0
            with sftp.file(remote_path, "wb") as remote_stream:
                remote_stream.set_pipelined(True)
                while True:
                    chunk = reader(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    remote_stream.write(chunk)
                    transferred_bytes += len(chunk)
                    if progress_callback:
                        progress_callback(transferred_bytes, total_bytes)
                remote_stream.flush()
            try:
                remote_size = int(sftp.stat(remote_path).st_size)
            except Exception:  # noqa: BLE001
                remote_size = total_bytes
            if remote_size != total_bytes:
                raise ApiError(f"远程上传大小异常: 预期 {total_bytes} 字节, 实际 {remote_size} 字节")
            return remote_path

    def upload_bytes(self, data: bytes, remote_path: str, progress_callback=None) -> str:
        """上传字节数据到远程路径，使用 _upload_reader 方法分块上传，确保大文件也能稳定上传。"""
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
        """上传本地文件到远程路径，使用 _upload_reader 方法分块上传，确保大文件也能稳定上传。"""
        source_path = Path(local_path)
        try:
            source_stat = source_path.stat()
            total_bytes = int(source_stat.st_size)
        except OSError as exc:
            raise ApiError(f"读取本地待上传文件失败: {source_path}") from exc
        with source_path.open("rb") as local_stream:
            uploaded_path = self._upload_reader(local_stream.read, total_bytes, remote_path, progress_callback=progress_callback)
        try:
            self.get_sftp(refresh=True).chmod(uploaded_path, source_stat.st_mode & 0o777)
        except OSError as exc:
            raise ApiError(f"同步远端文件权限失败: {uploaded_path}") from exc
        return uploaded_path

    def upload_local_tree(self, local_dir: str | Path, remote_dir: str) -> list[str]:
        """上传本地目录及其所有子文件到远程目录，保持目录结构，返回已上传的远程路径列表。"""
        source_dir = Path(local_dir)
        if not source_dir.exists():
            raise ApiError(f"本地目录不存在: {source_dir}")
        if not source_dir.is_dir():
            raise ApiError(f"本地路径不是目录: {source_dir}")
        remote_dir = self.resolve_remote_path(remote_dir)
        uploaded_paths: list[str] = []
        self.ensure_remote_dir(remote_dir)
        for path in sorted(source_dir.rglob("*")):
            relative_path = path.relative_to(source_dir).as_posix()
            target_path = posixpath.join(remote_dir, relative_path)
            if path.is_dir():
                self.ensure_remote_dir(target_path)
                continue
            self.upload_local_file(path, target_path)
            uploaded_paths.append(target_path)
        return uploaded_paths

    def list_dir(self, remote_dir: str) -> list[dict[str, Any]]:
        """列出远程目录下的所有文件和子目录，返回包含 name、path、is_dir、size、mtime 等信息的字典列表。"""
        with self.lock:
            self.ensure_connected()
            sftp = self.get_sftp()
            remote_dir = self.resolve_remote_path(remote_dir)
            entries = []
            for item in sftp.listdir_attr(remote_dir):
                if str(item.filename or "").strip() in IGNORED_REMOTE_ENTRY_NAMES:
                    continue
                path = posixpath.join(remote_dir, item.filename)
                entries.append(
                    {
                        "name": item.filename,
                        "path": path,
                        "is_dir": is_dir(item.st_mode),
                        "size": item.st_size,
                        "mtime": int(getattr(item, "st_mtime", 0) or 0),
                    }
                )
            entries.sort(key=lambda entry: (not entry["is_dir"], entry["name"].lower()))
            return entries

    def read_file_bytes(self, remote_path: str) -> bytes:
        """读取远程文件的字节内容，返回完整数据。确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        with self.lock:
            self.ensure_connected()
            sftp = self.get_sftp()
            remote_path = self.resolve_remote_path(remote_path)
            with sftp.file(remote_path, "rb") as remote_stream:
                return remote_stream.read()

    def path_exists(self, remote_path: str, *, refresh: bool = False) -> bool:
        """检查远程路径是否存在，返回 True 或 False。确保在调用前已连接机器人，否则抛出异常提示先连接机器人。"""
        with self.lock:
            self.ensure_connected()
            sftp = self.get_sftp(refresh=refresh)
            remote_path = self.resolve_remote_path(remote_path)
            try:
                sftp.stat(remote_path)
                return True
            except FileNotFoundError:
                return False

    def get_remote_file_owner(self, remote_path: str) -> str:
        """获取远程文件的所有者用户名，返回用户名字符串。确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        remote_path = self.resolve_remote_path(remote_path)
        result = self.exec_command(f"stat -c '%U' -- {shlex.quote(remote_path)}")
        if result["exit_code"] != 0:
            raise ApiError(f"读取远端文件所有者失败: {short_error(result)}")
        return str(result.get("stdout") or "").strip()

    def ensure_remote_executable(self, remote_path: str, *, sudo_password: str = "") -> dict[str, Any]:
        """确保远程文件具有可执行权限，如果没有则添加。
            支持使用 sudo 提权执行，确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        remote_path = self.resolve_remote_path(remote_path)
        command = f"chmod +x -- {shlex.quote(remote_path)}"
        result = self.exec_command(command, timeout=15.0)
        if result["exit_code"] != 0 and sudo_password:
            stderr_text = str(result.get("stderr") or "").lower()
            stdout_text = str(result.get("stdout") or "").lower()
            combined_text = f"{stdout_text}\n{stderr_text}"
            permission_related = (
                "permission denied" in combined_text
                or "operation not permitted" in combined_text
                or "not permitted" in combined_text
            )
            if permission_related:
                result = self.exec_sudo_command(command, sudo_password, timeout=20.0)
        if result["exit_code"] != 0:
            raise ApiError(f"设置远端文件可执行权限失败: {short_error(result)}")
        return result

    def is_dir_path(self, remote_path: str) -> bool:
        """检查远程路径是否是目录，返回 True 或 False。确保在调用前已连接机器人，否则抛出异常提示先连接机器人。"""
        with self.lock:
            self.ensure_connected()
            sftp = self.get_sftp()
            remote_path = self.resolve_remote_path(remote_path)
            try:
                return is_dir(sftp.stat(remote_path).st_mode)
            except FileNotFoundError:
                return False

    def backup_remote_path(self, remote_path: str, *, sudo_password: str = "") -> str | None:
        """备份远程路径到同目录下的备份文件，返回备份文件的路径。
            支持使用 sudo 提权执行，确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        remote_path = self.resolve_remote_path(remote_path)
        if not self.path_exists(remote_path):
            return None
        backup_path = build_backup_path(remote_path)
        command = f"cp -a -- {shlex.quote(remote_path)} {shlex.quote(backup_path)}"
        if sudo_password:
            result = self.exec_sudo_command(command, sudo_password)
        else:
            result = self.exec_command(command)
        if result["exit_code"] != 0:
            raise ApiError(f"远程备份失败: {short_error(result)}")
        return backup_path

    def restore_backup(self, backup_path: str, remote_path: str) -> dict[str, Any]:
        """从备份文件恢复远程路径，确保在调用前已连接机器人，并且备份路径存在，否则抛出异常提示错误原因。"""
        backup_path = self.resolve_remote_path(backup_path)
        remote_path = self.resolve_remote_path(remote_path)
        result = self.exec_command(f"cp -a -- {shlex.quote(backup_path)} {shlex.quote(remote_path)}")
        if result["exit_code"] != 0:
            raise ApiError(f"恢复备份失败: {short_error(result)}")
        return result

    def move_remote_path(self, source_path: str, target_path: str, *, sudo_password: str = "") -> dict[str, Any]:
        """移动远程路径到新位置，支持重命名或移动到不同目录，返回执行结果字典。"""
        source_path = self.resolve_remote_path(source_path)
        target_path = self.resolve_remote_path(target_path)
        self.ensure_remote_dir(posixpath.dirname(target_path))
        command = f"mv -f -- {shlex.quote(source_path)} {shlex.quote(target_path)}"
        if sudo_password:
            result = self.exec_sudo_command(command, sudo_password)
        else:
            result = self.exec_command(command)
        if result["exit_code"] != 0:
            raise ApiError(f"移动远端文件失败: {short_error(result)}")
        return result

    def remove_remote_path(self, remote_path: str, *, recursive: bool = False, sudo_password: str = "") -> dict[str, Any]:
        """删除远程路径，支持文件和目录（递归删除），返回完整删除结果。"""
        target_path = self.resolve_remote_path(remote_path)
        existed_before = self.path_exists(target_path)
        debug_prefix = f"[remove_remote_path] path={target_path} recursive={recursive} sudo={bool(sudo_password)}"
        print(f"{debug_prefix} existed_before={existed_before}", flush=True)
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
        print(f"{debug_prefix} command={raw_command}", flush=True)
        if sudo_password:
            result = self.exec_sudo_command(raw_command, sudo_password)
        else:
            result = self.exec_command(raw_command)
        print(
            f"{debug_prefix} exit_code={result.get('exit_code')} "
            f"stdout={str(result.get('stdout') or '').strip()!r} "
            f"stderr={str(result.get('stderr') or '').strip()!r}",
            flush=True,
        )
        if result["exit_code"] != 0:
            raise ApiError(f"删除远端路径失败: {short_error(result)}")
        print(f"{debug_prefix} checking_exists_after", flush=True)
        exists_after = self.path_exists(target_path, refresh=True)
        print(f"{debug_prefix} exists_after={exists_after}", flush=True)
        if exists_after:
            raise ApiError(f"删除命令已执行，但远端路径仍存在: {target_path}")
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
        """删除远程目录下所有以指定前缀开头的文件，返回已删除的文件路径列表。
            支持使用 sudo 提权执行，确保在调用前已连接机器人，并且目录存在，否则抛出异常提示错误原因。"""
        target_dir = self.resolve_remote_path(remote_dir)
        if not self.path_exists(target_dir):
            return []
        normalized_prefix = str(prefix or "").strip()
        if not normalized_prefix:
            raise ApiError("prefix 不能为空")

        # 直接在远端用 find 删除，避免先通过 SFTP 列出整个 /tmp 等大目录导致长时间卡住。
        pattern = shlex.quote(f"{normalized_prefix}*")
        command = (
            f"find {shlex.quote(target_dir)} -maxdepth 1 -type f "
            f"-name {pattern} -print -delete"
        )
        if sudo_password:
            result = self.exec_sudo_command(command, sudo_password, timeout=60.0)
        else:
            result = self.exec_command(command, timeout=60.0)
        if result["exit_code"] != 0:
            raise ApiError(f"删除旧文件失败: {short_error(result)}")
        removed_files = [
            line.strip()
            for line in str(result.get("stdout") or "").splitlines()
            if line.strip()
        ]
        return removed_files

    def walk_entries(self, root_path: str) -> list[dict[str, Any]]:
        """递归遍历远程目录及其子目录，返回包含所有文件和目录信息的字典列表。
            确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        results: list[dict[str, Any]] = []
        self._walk(self.resolve_remote_path(root_path), results)
        return results

    def list_files_recursive(self, root_path: str, *, require_birth_time: bool = False) -> list[dict[str, Any]]:
        """递归列出远程目录下的所有文件，返回包含 name、path、relative_path、size、mtime、ctime、birth_time 等信息的字典列表。
            使用 find 命令获取文件信息，确保兼容各种文件系统和环境。
            如果 require_birth_time=True 则要求文件系统必须支持创建时间，否则抛出异常提示不支持按创建时间筛选。
            确保在调用前已连接机器人，并且路径存在，否则抛出异常提示错误原因。"""
        resolved_root = self.resolve_remote_path(root_path)
        command = (
            f"find {shlex.quote(resolved_root)} -type f "
            "-exec stat -c '%W\t%Z\t%Y\t%s\t%n' {} +"
        )
        result = self.exec_command(command)
        if result["exit_code"] != 0:
            raise ApiError(f"递归扫描日志目录失败: {short_error(result)}")

        entries: list[dict[str, Any]] = []
        for raw_line in iter_command_output_lines(result.get("stdout") or ""):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("\t", 4)
            if len(parts) != 5:
                continue
            birth_time_raw, change_time_raw, modified_time_raw, size_raw, path = parts
            try:
                birth_time = int(float(birth_time_raw or 0))
            except ValueError:
                birth_time = 0
            try:
                change_time = int(float(change_time_raw or 0))
            except ValueError:
                change_time = 0
            try:
                modified_time = int(float(modified_time_raw or 0))
            except ValueError:
                modified_time = 0
            try:
                size = int(float(size_raw or 0))
            except ValueError:
                size = 0
            normalized_path = str(path or "").strip()
            if not normalized_path:
                continue
            if require_birth_time and birth_time <= 0:
                raise ApiError(f"文件系统不支持按创建时间筛选，缺少 birth time: {normalized_path}")
            relative_path = posixpath.relpath(normalized_path, resolved_root)
            entries.append(
                {
                    "name": posixpath.basename(normalized_path),
                    "path": normalized_path,
                    "relative_path": relative_path,
                    "is_dir": False,
                    "size": size,
                    "mtime": modified_time,
                    "ctime": change_time,
                    "birth_time": birth_time,
                    "created_at": birth_time,
                }
            )
        entries.sort(
            key=lambda entry: (
                posixpath.dirname(str(entry.get("relative_path") or "")),
                str(entry.get("name") or "").lower(),
                str(entry.get("relative_path") or "").lower(),
            )
        )
        return entries

    def directory_shortcuts(self) -> dict[str, Any]:
        """提供一组常用的远程目录快捷方式，返回包含 shortcuts 列表和 preferred_root 字段的字典。
            shortcuts 列表包含 label、path、display_path、exists 等信息，
            preferred_root 是推荐的默认项目根目录路径。确保在调用前已连接机器人，否则抛出"""
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
        base_shortcuts = [
            {"label": "机器人 Home", "path": home_dir, "display_path": "~", "exists": True},
            {"label": "临时目录 /tmp", "path": "/tmp", "display_path": "/tmp", "exists": self.path_exists("/tmp")},
            {"label": "根目录 /", "path": "/", "display_path": "/", "exists": True},
        ]
        for shortcut in base_shortcuts:
            if shortcut["path"] in seen_paths:
                continue
            seen_paths.add(shortcut["path"])
            shortcuts.append(shortcut)
        if not preferred_root:
            preferred_root = home_dir
        return {"shortcuts": shortcuts, "preferred_root": preferred_root}

    def _walk(self, current: str, output: list[dict[str, Any]]) -> None:
        """"递归遍历远程目录，内部使用 list_dir 获取当前目录的条目，并将结果追加到 output 列表中。
            对于每个子目录，继续递归调用 _walk 进行遍历，确保最终 output 包含所有文件和目录的信息。"""
        for entry in self.list_dir(current):
            output.append(entry)
            if entry["is_dir"]:
                try:
                    self._walk(entry["path"], output)
                except OSError:
                    continue
