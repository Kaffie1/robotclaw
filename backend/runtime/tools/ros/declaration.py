from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.core.config import ROSBRIDGE_SERVICE_NAME, ROS_COMPOSE_PROJECT_ROOT
from ..base import ToolRuntime, connected_tool
from ..docker import DockerComposeExecArgs, handle_docker_compose_exec_command
from .impl import (
    ros_list_services,
    ros_list_topics,
    ros_message_definition,
    ros_service_call,
    ros_service_definition_by_type,
    ros_service_info,
    ros_service_type,
    ros_topic_echo,
    ros_topic_info,
    ros_topic_type,
)


class RosNameArgs(BaseModel):
    name: str


class RosTypeNameArgs(BaseModel):
    type_name: str


class RosServiceCallArgs(BaseModel):
    name: str
    request: Any | None = None


class RosComposeExecArgs(BaseModel):
    device_type: str = "ORIN"
    service_name: str = ROSBRIDGE_SERVICE_NAME
    command: str
    timeout_seconds: int = 30


@connected_tool
def handle_ros_list_topics(args: BaseModel, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_list_topics(runtime.client)


@connected_tool
def handle_ros_list_services(args: BaseModel, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_list_services(runtime.client)


@connected_tool
def handle_ros_topic_info(args: RosNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_topic_info(runtime.client, args.name)


@connected_tool
def handle_ros_topic_type(args: RosNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_topic_type(runtime.client, args.name)


@connected_tool
def handle_ros_message_definition(args: RosTypeNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_message_definition(runtime.client, args.type_name)


@connected_tool
def handle_ros_topic_echo(args: RosNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_topic_echo(runtime.client, args.name, timeout=15.0, line_limit=120)


@connected_tool
def handle_ros_service_info(args: RosNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_service_info(runtime.client, args.name)


@connected_tool
def handle_ros_service_type(args: RosNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_service_type(runtime.client, args.name)


@connected_tool
def handle_ros_service_definition(args: RosTypeNameArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_service_definition_by_type(runtime.client, args.type_name)


@connected_tool
def handle_ros_service_call(args: RosServiceCallArgs, runtime: ToolRuntime) -> dict[str, Any]:
    return ros_service_call(runtime.client, args.name, args.request)


def handle_ros_compose_exec_command(args: RosComposeExecArgs, tool_context: dict[str, object] | None) -> dict[str, object]:
    generic_args = DockerComposeExecArgs(
        device_type=args.device_type,
        project_root=ROS_COMPOSE_PROJECT_ROOT,
        service_name=args.service_name,
        command=args.command,
        timeout_seconds=args.timeout_seconds,
    )
    return handle_docker_compose_exec_command(generic_args, tool_context)
