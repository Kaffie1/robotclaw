from __future__ import annotations

import shlex

from backend.ssh import RemoteCommand
from backend.tools.models import (
    FieldType,
    Tool,
    ToolExecuteResult,
    ToolParams,
    build_field_schema,
    build_tool_result,
    build_tool_result_schema,
)
from backend.tools.specs.common import (
    public_params,
    ssh_not_configured,
    summarize_command_output,
)


def build_ping_host_input_schema() -> dict[str, dict]:
    return {
        "host": build_field_schema(FieldType.kString, description="目标 IP 或主机名"),
        "count": build_field_schema(FieldType.kInt, description="ping 次数"),
        "timeout_seconds": build_field_schema(FieldType.kInt, description="单次超时", unit="s"),
    }


def build_ping_host_output_schema() -> dict[str, dict]:
    return {
        "exit_code": build_field_schema(FieldType.kInt, description="ping 退出码"),
        "stdout": build_field_schema(FieldType.kString, description="标准输出"),
        "stderr": build_field_schema(FieldType.kString, description="标准错误"),
    }


def build_ping_host_tool() -> Tool:
    return Tool(
        name="ping_host",
        input_schema=build_ping_host_input_schema(),
        output_schema=build_ping_host_output_schema(),
        result_schema=build_tool_result_schema(build_ping_host_output_schema()),
        execute=execute_ping_host,
    )


def execute_ping_host(params: ToolParams) -> ToolExecuteResult:
    call_id = str(params.get("_call_id") or "").strip()
    tool = params.get("_tool")
    ssh_manager = params.get("_ssh_manager")
    host = str(params.get("host", "") or "").strip()
    count = _to_positive_int(params.get("count"), default=1)
    timeout_seconds = _to_positive_int(params.get("timeout_seconds"), default=2)

    if not host:
        return build_tool_result(
            call_id=call_id,
            tool_name="ping_host",
            success=False,
            status="failed",
            facts={"reason": "missing_host"},
            summary="缺少目标地址，无法执行网络连通性检查。",
            error="missing_host",
            data={
                "params": public_params(params),
                "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
            },
            raw_output="",
        )

    if ssh_manager is None or not hasattr(ssh_manager, "run_command"):
        return ssh_not_configured(
            call_id=call_id,
            params=params,
            tool_name="ping_host",
            tool=tool if isinstance(tool, Tool) else None,
        )

    remote_command = RemoteCommand(
        command=(
            f"ping -c {count} -W {timeout_seconds} "
            f"{shlex.quote(host)}"
        ),
        timeout_sec=max(count * timeout_seconds + 5, 6),
    )
    command_result = ssh_manager.run_command(remote_command)
    summary = summarize_command_output(command_result.stdout, command_result.stderr)
    if command_result.exit_code == 0:
        summary = summary or f"{host} 网络连通正常。"
    else:
        summary = summary or f"{host} ping 失败。"

    result = build_tool_result(
        call_id=call_id,
        tool_name="ping_host",
        success=command_result.exit_code == 0,
        status="completed" if command_result.success else "failed",
        facts={
            "host": host,
            "reachable": command_result.exit_code == 0,
            "exit_code": int(command_result.exit_code),
        },
        summary=summary,
        data={
            "params": public_params(params),
            "output": {
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "exit_code": int(command_result.exit_code),
            },
            "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
        },
        error="" if command_result.exit_code == 0 else summary,
        raw_output=command_result.stdout or command_result.stderr or "",
    )
    return result


def _to_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
