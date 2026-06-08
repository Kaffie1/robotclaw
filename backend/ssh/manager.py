from __future__ import annotations

from threading import Lock

from backend.shared import now_iso
from backend.ssh.models import RobotConnectionConfig, SSHConnectionState


class SSHManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current_config = RobotConnectionConfig()
        self._current_state = SSHConnectionState()

    def connect(self, robot_ref: str, host: str) -> tuple[RobotConnectionConfig, SSHConnectionState]:
        with self._lock:
            self._current_config = RobotConnectionConfig(
                robot_ref=robot_ref,
                host=host,
                port=22,
                username="robot",
            )
            self._current_state = SSHConnectionState(
                connected=True,
                robot_ref=robot_ref,
                host=host,
                port=22,
                username="robot",
                connected_at=now_iso(),
            )
            return self._current_config, self._current_state

    def disconnect(self) -> tuple[RobotConnectionConfig, SSHConnectionState]:
        with self._lock:
            self._current_config = RobotConnectionConfig()
            self._current_state = SSHConnectionState()
            return self._current_config, self._current_state

    def current_config(self) -> RobotConnectionConfig:
        return self._current_config

    def current_state(self) -> SSHConnectionState:
        return self._current_state

    def ui_payload(self) -> dict:
        state = self.current_state()
        return {
            "connected": state.connected,
            "name": state.robot_ref,
            "host": state.host,
        }
