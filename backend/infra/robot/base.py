from abc import ABC, abstractmethod

from ...core.models import ConnectionConfig


class RobotClient(ABC):
    @property
    @abstractmethod
    def connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def connect(self, config: ConnectionConfig) -> None:
        raise NotImplementedError

    @abstractmethod
    def connect_via_jump(self, jump_client: "RobotClient", config: ConnectionConfig) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def ensure_connected(self) -> None:
        raise NotImplementedError
