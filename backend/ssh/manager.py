from __future__ import annotations

import shlex
from threading import Lock
from typing import Any

import paramiko

from backend.shared import get_logger, now_iso
from backend.ssh.models import RemoteCommand, RemoteCommandResult, RobotConnectionConfig, SSHConnectionState


logger = get_logger("ssh.manager")


class SSHManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current_config = RobotConnectionConfig()
        self._current_state = SSHConnectionState()
        self._client: paramiko.SSHClient | None = None

    def connect(
        self,
        config: RobotConnectionConfig | None = None,
        *,
        robot_ref: str = "",
        host: str = "",
        port: int = 22,
        username: str = "",
        password: str = "",
        private_key_path: str = "",
        ros_version: str = "",
        workspace: str = "",
        setup_script: str = "",
    ) -> tuple[RobotConnectionConfig, SSHConnectionState]:
        target = self._normalize_config(
            config,
            robot_ref=robot_ref,
            host=host,
            port=port,
            username=username,
            password=password,
            private_key_path=private_key_path,
            ros_version=ros_version,
            workspace=workspace,
            setup_script=setup_script,
        )

        with self._lock:
            self._disconnect_locked()
            self._current_config = target

            try:
                client = self._build_client()
                client.connect(
                    hostname=target.host,
                    port=target.port,
                    username=target.username,
                    password=target.password or None,
                    key_filename=target.private_key_path or None,
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10,
                )
            except Exception as exc:
                self._client = None
                self._current_state = SSHConnectionState(
                    connected=False,
                    robot_ref=target.robot_ref,
                    host=target.host,
                    port=target.port,
                    username=target.username,
                    last_error=str(exc),
                )
                logger.warning(
                    "SSH connect failed robot_ref=%s host=%s port=%s error=%s",
                    target.robot_ref,
                    target.host,
                    target.port,
                    exc,
                )
                return self._current_config, self._current_state

            self._client = client
            self._current_state = SSHConnectionState(
                connected=True,
                robot_ref=target.robot_ref,
                host=target.host,
                port=target.port,
                username=target.username,
                connected_at=now_iso(),
            )
            logger.info(
                "SSH connected robot_ref=%s host=%s port=%s username=%s",
                target.robot_ref,
                target.host,
                target.port,
                target.username,
            )
            return self._current_config, self._current_state

    def switch_config(self, config: RobotConnectionConfig) -> tuple[RobotConnectionConfig, SSHConnectionState]:
        return self.connect(config=config)

    def disconnect(self) -> tuple[RobotConnectionConfig, SSHConnectionState]:
        with self._lock:
            self._disconnect_locked()
            self._current_config = RobotConnectionConfig()
            self._current_state = SSHConnectionState()
            logger.info("SSH disconnected")
            return self._current_config, self._current_state

    def run_command(self, command: RemoteCommand) -> RemoteCommandResult:
        with self._lock:
            client = self._client
            state = self._current_state
            config = self._current_config

        if not state.connected or client is None:
            return RemoteCommandResult(success=False, exit_code=-1, stderr="ssh_not_connected")

        remote_command = self._wrap_command(command, config)

        try:
            _stdin, stdout, stderr = client.exec_command(
                remote_command,
                timeout=max(1, int(command.timeout_sec or 30)),
            )
            exit_code = int(stdout.channel.recv_exit_status())
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("SSH command failed command=%s error=%s", command.command, exc)
            return RemoteCommandResult(success=False, exit_code=-1, stderr=str(exc))

        return RemoteCommandResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    def current_config(self) -> RobotConnectionConfig:
        return self._current_config

    def current_state(self) -> SSHConnectionState:
        return self._current_state

    def ui_payload(self) -> dict:
        state = self.current_state()
        config = self.current_config()
        return {
            "connected": state.connected,
            "name": state.robot_ref,
            "host": state.host,
            "port": state.port,
            "username": state.username,
            "ros_version": config.ros_version,
            "workspace": config.workspace,
            "setup_script": config.setup_script,
            "last_error": state.last_error,
            "connected_at": state.connected_at,
        }

    def _disconnect_locked(self) -> None:
        if self._client is None:
            return
        try:
            self._client.close()
        except Exception as exc:
            logger.debug("SSH close ignored error=%s", exc)
        finally:
            self._client = None

    def _build_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _normalize_config(
        self,
        config: RobotConnectionConfig | None,
        **fallback: Any,
    ) -> RobotConnectionConfig:
        if config is not None:
            target = config
        else:
            target = RobotConnectionConfig(
                robot_ref=str(fallback.get("robot_ref", "")).strip() or "naviai",
                host=str(fallback.get("host", "")).strip() or "172.16.9.136",
                port=self._normalize_port(fallback.get("port", 22)),
                username=str(fallback.get("username", "")).strip() or "naviai",
                password=str(fallback.get("password", "") or "naviai@2024"),
                private_key_path=str(fallback.get("private_key_path", "") or "").strip(),
                ros_version=str(fallback.get("ros_version", "") or "").strip(),
                workspace=str(fallback.get("workspace", "") or "").strip(),
                setup_script=str(fallback.get("setup_script", "") or "").strip(),
            )

        return RobotConnectionConfig(
            robot_ref=str(target.robot_ref or "").strip() or "naviai",
            host=str(target.host or "").strip() or "172.16.9.136",
            port=self._normalize_port(target.port),
            username=str(target.username or "").strip() or "naviai",
            password=str(target.password or "naviai@2024"),
            private_key_path=str(target.private_key_path or "").strip(),
            ros_version=str(target.ros_version or "").strip(),
            workspace=str(target.workspace or "").strip(),
            setup_script=str(target.setup_script or "").strip(),
        )

    def _normalize_port(self, value: Any) -> int:
        try:
            port = int(value)
        except (TypeError, ValueError):
            port = 22
        return port if port > 0 else 22

    def _wrap_command(self, command: RemoteCommand, config: RobotConnectionConfig) -> str:
        steps: list[str] = []
        merged_env = {key: str(value) for key, value in command.env.items() if str(key).strip()}

        if merged_env:
            exports = " ".join(
                f"{shlex.quote(str(key))}={shlex.quote(str(value))}"
                for key, value in merged_env.items()
            )
            steps.append(f"export {exports}")

        cwd = str(command.cwd or "").strip() or config.workspace
        if cwd:
            steps.append(f"cd {shlex.quote(cwd)}")

        if config.setup_script:
            steps.append(f"source {shlex.quote(config.setup_script)}")

        steps.append(str(command.command or "").strip())
        shell_command = " && ".join(step for step in steps if step)
        return f"bash -lc {shlex.quote(shell_command)}"
