from ...core.config import IS_ROBOT_EDITION
from .base import RobotClient
from .local import LocalRobotClient
from .ssh import SshRobotClient


def create_runtime_client() -> RobotClient:
    if IS_ROBOT_EDITION:
        return LocalRobotClient()
    return SshRobotClient()


def create_ssh_client() -> SshRobotClient:
    return SshRobotClient()
