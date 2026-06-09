from __future__ import annotations

import shlex

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
    build_rosbridge_remote_command,
    public_params,
    ssh_not_configured,
    summarize_command_output,
)


def build_ros_topic_echo_input_schema() -> dict[str, dict]:
    return {
        "name": build_field_schema(FieldType.kString, description="ROS topic 名称"),
        "grep": build_field_schema(FieldType.kString, description="对 rostopic 输出执行 grep 过滤的关键字"),
        "timeout_seconds": build_field_schema(FieldType.kInt, description="采集超时", unit="s"),
    }


def build_ros_topic_echo_output_schema() -> dict[str, dict]:
    return {
        "exit_code": build_field_schema(FieldType.kInt, description="rostopic 命令退出码"),
        "stdout": build_field_schema(FieldType.kString, description="标准输出"),
        "stderr": build_field_schema(FieldType.kString, description="标准错误"),
    }


def build_ros_topic_echo_tool() -> Tool:
    return Tool(
        name="ros_topic_echo",
        input_schema=build_ros_topic_echo_input_schema(),
        output_schema=build_ros_topic_echo_output_schema(),
        result_schema=build_tool_result_schema(build_ros_topic_echo_output_schema()),
        execute=execute_ros_topic_echo,
    )


def execute_ros_topic_echo(params: ToolParams) -> ToolExecuteResult:
    call_id = str(params.get("_call_id") or "").strip()
    tool = params.get("_tool")
    ssh_manager = params.get("_ssh_manager")
    topic_name = str(params.get("name", "") or "").strip()
    grep_pattern = str(params.get("grep", "") or "").strip()
    timeout_seconds = _to_positive_int(params.get("timeout_seconds"), default=8)

    if not topic_name:
        return build_tool_result(
            call_id=call_id,
            tool_name="ros_topic_echo",
            success=False,
            status="failed",
            facts={"reason": "missing_topic_name"},
            summary="缺少 ROS topic 名称，无法采集话题数据。",
            error="missing_topic_name",
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
            tool_name="ros_topic_echo",
            tool=tool if isinstance(tool, Tool) else None,
        )

    remote_command = build_rosbridge_remote_command(
        _build_ros_topic_echo_command(topic_name, timeout_seconds, grep_pattern=grep_pattern),
        timeout_sec=timeout_seconds + 10,
    )
    command_result = ssh_manager.run_command(remote_command)
    summary = summarize_command_output(command_result.stdout, command_result.stderr)

    if "__RC_ERROR__=rostopic_not_found" in (command_result.stdout or ""):
        return build_tool_result(
            call_id=call_id,
            tool_name="ros_topic_echo",
            success=False,
            status="failed",
            facts={"topic": topic_name, "reason": "rostopic_not_found"},
            summary="远端环境未找到 rostopic 命令，暂时无法检查话题数据。",
            error="rostopic_not_found",
            data={
                "params": public_params(params),
                "output": {
                    "stdout": command_result.stdout,
                    "stderr": command_result.stderr,
                    "exit_code": int(command_result.exit_code),
                },
                "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
            },
            raw_output=command_result.stdout or "",
        )

    result = build_tool_result(
        call_id=call_id,
        tool_name="ros_topic_echo",
        success=bool(command_result.success),
        status="completed" if command_result.success else "failed",
        facts={
            "topic": topic_name,
            "grep": grep_pattern,
            "exit_code": int(command_result.exit_code),
        },
        summary=summary or f"topic {topic_name} 未返回可解析内容。",
        data={
            "params": public_params(params),
            "output": {
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "exit_code": int(command_result.exit_code),
            },
            "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
        },
        error="" if command_result.success else summary or "ros_topic_echo_failed",
        raw_output=command_result.stdout or command_result.stderr or "",
    )
    return result


def _build_ros_topic_echo_command(topic_name: str, timeout_seconds: int, *, grep_pattern: str = "") -> str:
    topic = shlex.quote(topic_name)
    base_command = (
        "if ! command -v rostopic >/dev/null 2>&1; then "
        "echo '__RC_ERROR__=rostopic_not_found'; exit 0; "
        "fi; "
        f"OUTPUT=$(timeout {timeout_seconds}s rostopic echo -n 1 {topic} 2>&1); "
        "STATUS=$?; "
        "if [ \"$STATUS\" -ne 0 ]; then "
        "printf '%s' \"$OUTPUT\"; "
        "exit \"$STATUS\"; "
        "fi; "
    )
    if grep_pattern:
        pattern = shlex.quote(grep_pattern)
        return (
            base_command
            + f"printf '%s' \"$OUTPUT\" | grep -F -- {pattern} || true"
        )
    return base_command + "printf '%s' \"$OUTPUT\""


def _to_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
