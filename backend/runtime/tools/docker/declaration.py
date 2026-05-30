from __future__ import annotations

from pydantic import BaseModel

from ..base import ToolRuntime, connected_tool, with_target_tool_runtime
from ..remote import DeviceTypeArgs
from .impl import (
    docker_compose_down_module,
    docker_compose_exec_command,
    docker_compose_up_module,
)


class DockerComposeModuleArgs(BaseModel):
    module_name: str


class DockerComposeExecArgs(DeviceTypeArgs):
    project_root: str
    service_name: str
    command: str
    timeout_seconds: int = 30


@connected_tool
def handle_docker_compose_down_module(args: DockerComposeModuleArgs, runtime: ToolRuntime) -> dict[str, object]:
    return docker_compose_down_module(runtime.client, args.module_name)


@connected_tool
def handle_docker_compose_up_module(args: DockerComposeModuleArgs, runtime: ToolRuntime) -> dict[str, object]:
    return docker_compose_up_module(runtime.client, args.module_name)


def handle_docker_compose_exec_command(args: DockerComposeExecArgs, tool_context: dict[str, object] | None) -> dict[str, object]:
    def _handler(runtime, target, _: bool):
        return docker_compose_exec_command(
            runtime.client,
            args.project_root,
            args.service_name,
            args.command,
            timeout_seconds=args.timeout_seconds,
            device_type=str(target.get("device_type") or args.device_type),
        )

    return with_target_tool_runtime(tool_context, device_type=args.device_type, handler=_handler)
