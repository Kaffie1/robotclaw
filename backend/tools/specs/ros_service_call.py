from __future__ import annotations

import json
import shlex
from typing import Any

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


def build_ros_service_call_input_schema() -> dict[str, dict]:
    return {
        "name": build_field_schema(FieldType.kString, description="ROS service 名称"),
        "request": build_field_schema(FieldType.kString, description="service 请求参数(JSON/YAML 风格文本)"),
        "timeout_seconds": build_field_schema(FieldType.kInt, description="调用超时", unit="s"),
    }


def build_ros_service_call_output_schema() -> dict[str, dict]:
    return {
        "exit_code": build_field_schema(FieldType.kInt, description="rosservice 命令退出码"),
        "stdout": build_field_schema(FieldType.kString, description="标准输出"),
        "stderr": build_field_schema(FieldType.kString, description="标准错误"),
    }


def build_ros_service_call_tool() -> Tool:
    return Tool(
        name="ros_service_call",
        input_schema=build_ros_service_call_input_schema(),
        output_schema=build_ros_service_call_output_schema(),
        result_schema=build_tool_result_schema(build_ros_service_call_output_schema()),
        execute=execute_ros_service_call,
    )


def execute_ros_service_call(params: ToolParams) -> ToolExecuteResult:
    call_id = str(params.get("_call_id") or "").strip()
    tool = params.get("_tool")
    ssh_manager = params.get("_ssh_manager")
    service_name = str(params.get("name", "") or "").strip()
    timeout_seconds = _to_positive_int(params.get("timeout_seconds"), default=15)

    if not service_name:
        return build_tool_result(
            call_id=call_id,
            tool_name="ros_service_call",
            success=False,
            status="failed",
            facts={"reason": "missing_service_name"},
            summary="缺少 ROS service 名称，无法执行服务调用。",
            error="missing_service_name",
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
            tool_name="ros_service_call",
            tool=tool if isinstance(tool, Tool) else None,
        )

    request_payload = _serialize_request(params.get("request"))
    remote_command = build_rosbridge_remote_command(
        _build_ros_service_call_command(service_name, request_payload, timeout_seconds),
        timeout_sec=timeout_seconds + 10,
    )
    command_result = ssh_manager.run_command(remote_command)
    summary = summarize_command_output(command_result.stdout, command_result.stderr)

    if "__RC_ERROR__=rosservice_not_found" in (command_result.stdout or ""):
        return build_tool_result(
            call_id=call_id,
            tool_name="ros_service_call",
            success=False,
            status="failed",
            facts={"service": service_name, "reason": "rosservice_not_found"},
            summary="远端环境未找到 rosservice 命令，暂时无法调用服务。",
            error="rosservice_not_found",
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
        tool_name="ros_service_call",
        success=bool(command_result.success),
        status="completed" if command_result.success else "failed",
        facts={
            "service": service_name,
            "exit_code": int(command_result.exit_code),
        },
        summary=summary or f"service {service_name} 未返回可解析内容。",
        data={
            "params": public_params(params),
            "request_payload": request_payload,
            "output": {
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "exit_code": int(command_result.exit_code),
            },
            "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
        },
        error="" if command_result.success else summary or "ros_service_call_failed",
        raw_output=command_result.stdout or command_result.stderr or "",
    )
    return result


def _build_ros_service_call_command(service_name: str, request_payload: str, timeout_seconds: int) -> str:
    service = shlex.quote(service_name)
    if request_payload:
        payload = shlex.quote(request_payload)
        command = f"timeout {timeout_seconds}s rosservice call {service} {payload} 2>&1"
    else:
        command = f"timeout {timeout_seconds}s rosservice call {service} 2>&1"
    return (
        "if ! command -v rosservice >/dev/null 2>&1; then "
        "echo '__RC_ERROR__=rosservice_not_found'; exit 0; "
        "fi; "
        f"{command}"
    )


def _serialize_request(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def _to_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
