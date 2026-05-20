from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator


@dataclass
class ConnectionConfig:
    host: str
    port: int
    username: str
    password: str = ""
    timeout: int = 10


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


class TaskFailure(Exception):
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


class ConnectPayload(BaseModel):
    host: str
    port: int
    username: str
    password: str = ""
    pico_host: str = ""
    pico_port: int = 22
    pico_username: str = ""
    pico_password: str = ""


class InstallDebPayload(BaseModel):
    remote_path: str
    command_template: str = "dpkg -i {deb_path}"


class ExecutePayload(BaseModel):
    command: str
    interactive: bool = False
    device_type: str = "ORIN"


class RosTopicPublishPayload(BaseModel):
    name: str
    message_type: str
    message: str = ""


class RosServiceCallPayload(BaseModel):
    name: str
    request: str = ""


class ToolCallPayload(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_tool_call_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        upgraded = dict(data)
        if not upgraded.get("name") and upgraded.get("tool_name"):
            upgraded["name"] = upgraded.get("tool_name")
        if not isinstance(upgraded.get("arguments"), dict) and isinstance(upgraded.get("args"), dict):
            upgraded["arguments"] = upgraded.get("args")
        return upgraded
