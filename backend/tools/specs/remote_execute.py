from __future__ import annotations

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


def build_remote_execute_input_schema() -> dict[str, dict]:
    return {
        "command": build_field_schema(FieldType.kString, description="远程命令"),
        "cwd": build_field_schema(FieldType.kString, description="远程命令执行目录"),
        "timeout_seconds": build_field_schema(FieldType.kInt, description="超时时间", unit="s"),
    }


def build_remote_execute_output_schema() -> dict[str, dict]:
    return {
        "exit_code": build_field_schema(FieldType.kInt, description="远程命令退出码"),
        "stdout": build_field_schema(FieldType.kString, description="标准输出"),
        "stderr": build_field_schema(FieldType.kString, description="标准错误"),
    }


def build_remote_execute_tool() -> Tool:
    return Tool(
        name="remote_execute",
        input_schema=build_remote_execute_input_schema(),
        output_schema=build_remote_execute_output_schema(),
        result_schema=build_tool_result_schema(build_remote_execute_output_schema()),
        execute=execute_remote_execute,
    )


def execute_remote_execute(params: ToolParams) -> ToolExecuteResult:
    call_id = str(params.get("_call_id") or "").strip()
    tool = params.get("_tool")
    ssh_manager = params.get("_ssh_manager")
    command = str(params.get("command", "") or "").strip()
    cwd = str(params.get("cwd", "") or "").strip()
    timeout_seconds = _to_positive_int(params.get("timeout_seconds"), default=30)

    if not command:
        return build_tool_result(
            call_id=call_id,
            tool_name="remote_execute",
            success=False,
            status="failed",
            facts={"reason": "missing_command"},
            summary="缺少远程命令，无法执行检查。",
            error="missing_command",
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
            tool_name="remote_execute",
            tool=tool if isinstance(tool, Tool) else None,
        )

    command_result = ssh_manager.run_command(
        RemoteCommand(
            command=command,
            timeout_sec=timeout_seconds,
            cwd=cwd,
        )
    )
    summary = summarize_command_output(command_result.stdout, command_result.stderr)
    result = build_tool_result(
        call_id=call_id,
        tool_name="remote_execute",
        success=bool(command_result.success),
        status="completed" if command_result.success else "failed",
        facts={
            "command": command,
            "cwd": cwd,
            "exit_code": int(command_result.exit_code),
        },
        summary=summary or f"命令已执行完成，退出码 {command_result.exit_code}。",
        data={
            "params": public_params(params),
            "output": {
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "exit_code": int(command_result.exit_code),
            },
            "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
        },
        error="" if command_result.success else summary or "remote_command_failed",
        raw_output=command_result.stdout or command_result.stderr or "",
    )
    return result


def _to_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
