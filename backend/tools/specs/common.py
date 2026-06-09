from __future__ import annotations

import shlex

from backend.ssh import RemoteCommand
from backend.tools.models import Tool, ToolExecuteResult, ToolParams, build_tool_result, schema_to_payload


ROSBRIDGE_PROJECT_DIR = "/home/naviai/navi_project"
ROSBRIDGE_SERVICE_NAME = "rosbridge"


def public_params(params: ToolParams) -> dict[str, object]:
    return {key: value for key, value in params.items() if not str(key).startswith("_")}


def unavailable_result(
    *,
    call_id: str,
    params: ToolParams,
    tool_name: str,
    tool: Tool | None,
    error: str,
    summary: str,
) -> ToolExecuteResult:
    return build_tool_result(
        call_id=call_id,
        tool_name=tool_name,
        success=False,
        status="unavailable",
        facts={"reason": error, "params": public_params(params)},
        summary=summary,
        error=error,
        data={
            "params": public_params(params),
            "input_schema": schema_to_payload(tool.input_schema) if tool else {},
            "output_schema": schema_to_payload(tool.output_schema) if tool else {},
            "result_schema": dict(tool.result_schema) if tool else {},
        },
        raw_output="",
    )


def ssh_not_configured(
    *,
    call_id: str,
    params: ToolParams,
    tool_name: str,
    tool: Tool | None,
) -> ToolExecuteResult:
    return unavailable_result(
        call_id=call_id,
        params=params,
        tool_name=tool_name,
        tool=tool,
        error="ssh_manager_not_configured",
        summary=f"SSH 管理器未配置，无法执行 {tool_name}。",
    )


def summarize_command_output(stdout: str, stderr: str) -> str:
    text = str(stdout or "").strip()
    if text:
        return text
    return str(stderr or "").strip()


def build_rosbridge_remote_command(
    inner_command: str,
    *,
    timeout_sec: int = 30,
    project_dir: str = ROSBRIDGE_PROJECT_DIR,
    service_name: str = ROSBRIDGE_SERVICE_NAME,
) -> RemoteCommand:
    wrapped = (
        f"docker compose exec -T {shlex.quote(service_name)} "
        f"bash -lc {shlex.quote(str(inner_command or '').strip())}"
    )
    return RemoteCommand(
        command=wrapped,
        timeout_sec=timeout_sec,
        cwd=project_dir,
    )
