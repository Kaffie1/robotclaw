from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RobotConnectionConfig:
    robot_ref: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    private_key_path: str = ""
    ros_version: str = ""
    workspace: str = ""
    setup_script: str = ""


@dataclass
class SSHConnectionState:
    connected: bool = False
    robot_ref: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    last_error: str = ""
    connected_at: str = ""
