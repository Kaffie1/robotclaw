from __future__ import annotations

from datetime import datetime, timezone
import re

from backend.ssh import RemoteCommand, SSHManager
from backend.tools.models import (
    FieldType,
    Tool,
    ToolParams,
    ToolExecuteResult,
    build_field_schema,
    build_tool_result,
    build_tool_result_schema,
    schema_to_payload,
)
from backend.tools.specs.common import build_rosbridge_remote_command


_EXISTS_RE = re.compile(r"__RC_TOPIC_EXISTS__=(?P<value>[01])")
_REMOTE_TS_RE = re.compile(r"__RC_REMOTE_TS__=(?P<value>\d+(?:\.\d+)?)")
_HZ_RE = re.compile(r"average rate:\s*(?P<value>\d+(?:\.\d+)?)", re.IGNORECASE)
_ROS1_STAMP_RE = re.compile(r"stamp:\s*\n(?:[ \t].*\n)*?[ \t]*secs:\s*(?P<secs>\d+)\s*\n[ \t]*nsecs:\s*(?P<nsecs>\d+)", re.IGNORECASE)
_ROS2_STAMP_RE = re.compile(r"stamp:\s*\n(?:[ \t].*\n)*?[ \t]*sec:\s*(?P<secs>\d+)\s*\n[ \t]*nanosec:\s*(?P<nsecs>\d+)", re.IGNORECASE)


def build_topic_monitor_input_schema() -> dict[str, dict]:
    return {
        "topic": build_field_schema(FieldType.kString, description="ROS topic 名称"),
    }


def build_topic_monitor_output_schema() -> dict[str, dict]:
    return {
        "exists": build_field_schema(FieldType.kBool, description="ROS master 上是否存在该 topic"),
        "has_msg": build_field_schema(FieldType.kBool, description="是否收到过消息"),
        "age": build_field_schema(FieldType.kDouble, description="距离上次收到消息的时间", unit="s"),
        "hz": build_field_schema(FieldType.kDouble, description="topic 频率", unit="Hz"),
        "last_msg_time": build_field_schema(FieldType.kTimestamp, description="最后一次收到消息的时间"),
    }


def build_topic_monitor_tool() -> Tool:
    return Tool(
        name="topic_monitor",
        input_schema=build_topic_monitor_input_schema(),
        output_schema=build_topic_monitor_output_schema(),
        result_schema=build_tool_result_schema(build_topic_monitor_output_schema()),
        execute=execute_topic_monitor,
    )


def execute_topic_monitor(params: ToolParams) -> ToolExecuteResult:
    topic = str(params.get("topic", "") or "").strip()
    call_id = str(params.get("_call_id") or "").strip()
    tool = params.get("_tool")
    ssh_manager = params.get("_ssh_manager")
    if not topic:
        return build_tool_result(
            call_id=call_id,
            tool_name="topic_monitor",
            success=False,
            status="failed",
            facts={"reason": "missing_topic"},
            summary="topic_monitor 缺少 topic 参数。",
            error="missing_topic",
            data={
                "params": _public_params(params),
                "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
            },
        )

    if ssh_manager is None or not hasattr(ssh_manager, "run_command"):
        return _unavailable(
            call_id=call_id,
            params=params,
            tool=tool if isinstance(tool, Tool) else None,
            error="ssh_manager_not_configured",
            summary="SSH 管理器未配置，无法执行 topic_monitor。",
        )

    command_result = ssh_manager.run_command(_build_topic_monitor_remote_command(topic))
    if not command_result.success and not command_result.stdout:
        return build_tool_result(
            call_id=call_id,
            tool_name="topic_monitor",
            success=False,
            status="failed",
            facts={"topic": topic, "reason": command_result.stderr or "remote_command_failed"},
            summary=f"topic {topic} 采集失败。",
            error=command_result.stderr or "remote_command_failed",
            data={
                "params": _public_params(params),
                "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
            },
            raw_output=command_result.stderr,
        )

    raw_output = command_result.stdout or ""
    if "__RC_ERROR__=rostopic_not_found" in raw_output:
        return build_tool_result(
            call_id=call_id,
            tool_name="topic_monitor",
            success=False,
            status="failed",
            facts={"topic": topic, "reason": "rostopic_not_found"},
            summary="远端环境未找到 rostopic 命令。",
            error="rostopic_not_found",
            data={
                "params": _public_params(params),
                "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
            },
            raw_output=raw_output,
        )

    facts = _parse_topic_monitor_output(raw_output)
    facts["topic"] = topic
    summary = _build_summary(topic, facts)
    return build_tool_result(
        call_id=call_id,
        tool_name="topic_monitor",
        success=True,
        status="completed",
        facts=facts,
        summary=summary,
        data={
            "params": _public_params(params),
            "output": facts,
            "result_schema": dict(tool.result_schema) if isinstance(tool, Tool) else {},
        },
        raw_output=raw_output,
    )


def _build_topic_monitor_command(topic: str) -> str:
    escaped = topic.replace("\\", "\\\\").replace("\"", "\\\"")
    return (
        "if ! command -v rostopic >/dev/null 2>&1; then "
        "echo '__RC_ERROR__=rostopic_not_found'; exit 0; "
        "fi; "
        f"TOPIC=\"{escaped}\"; "
        "EXISTS=0; "
        "rostopic list 2>/dev/null | grep -Fx -- \"$TOPIC\" >/dev/null 2>&1 && EXISTS=1; "
        "echo \"__RC_TOPIC_EXISTS__=$EXISTS\"; "
        "if [ \"$EXISTS\" != \"1\" ]; then exit 0; fi; "
        "echo \"__RC_REMOTE_TS__=$(date +%s.%N)\"; "
        "echo '__RC_ECHO_BEGIN__'; "
        "timeout 5s rostopic echo -n 1 \"$TOPIC\" 2>&1 || true; "
        "echo '__RC_ECHO_END__'; "
        "echo '__RC_HZ_BEGIN__'; "
        "timeout 8s rostopic hz -w 3 \"$TOPIC\" 2>&1 || true; "
        "echo '__RC_HZ_END__'"
    )


def _build_topic_monitor_remote_command(topic: str) -> RemoteCommand:
    return build_rosbridge_remote_command(
        _build_topic_monitor_command(topic),
        timeout_sec=15,
    )


def _parse_topic_monitor_output(raw_output: str) -> dict:
    exists_match = _EXISTS_RE.search(raw_output)
    exists = bool(exists_match and exists_match.group("value") == "1")
    remote_ts_match = _REMOTE_TS_RE.search(raw_output)
    remote_ts = float(remote_ts_match.group("value")) if remote_ts_match else 0.0
    echo_output = _slice_block(raw_output, "__RC_ECHO_BEGIN__", "__RC_ECHO_END__")
    hz_output = _slice_block(raw_output, "__RC_HZ_BEGIN__", "__RC_HZ_END__")
    hz_match = _HZ_RE.search(hz_output)
    hz = float(hz_match.group("value")) if hz_match else 0.0
    has_msg = _detect_message_presence(echo_output)
    stamp = _extract_header_stamp(echo_output)

    age = -1.0
    last_msg_time = ""
    if stamp is not None:
        last_msg_time = datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        if remote_ts > 0:
            age = round(max(0.0, remote_ts - stamp), 3)

    return {
        "exists": exists,
        "has_msg": has_msg,
        "age": age,
        "hz": hz,
        "last_msg_time": last_msg_time,
    }


def _slice_block(raw_output: str, begin: str, end: str) -> str:
    if begin not in raw_output or end not in raw_output:
        return ""
    return raw_output.split(begin, 1)[1].split(end, 1)[0].strip()


def _detect_message_presence(echo_output: str) -> bool:
    content = str(echo_output or "").strip()
    if not content:
        return False
    lowered = content.lower()
    bad_markers = [
        "warning: no messages received",
        "does not appear to be published yet",
        "unable to communicate with master",
        "unknown topic",
        "cannot load message class",
    ]
    return not any(marker in lowered for marker in bad_markers)


def _extract_header_stamp(echo_output: str) -> float | None:
    for pattern in (_ROS1_STAMP_RE, _ROS2_STAMP_RE):
        match = pattern.search(echo_output)
        if match:
            secs = int(match.group("secs"))
            nsecs = int(match.group("nsecs"))
            return secs + nsecs / 1_000_000_000
    return None


def _build_summary(topic: str, facts: dict) -> str:
    if not facts["exists"]:
        return f"topic {topic} 不存在。"
    if not facts["has_msg"]:
        return f"topic {topic} 已注册，但暂未收到消息。"

    pieces = [f"topic {topic} 有消息"]
    if facts["hz"] > 0:
        pieces.append(f"频率约 {facts['hz']:.2f} Hz")
    if facts["age"] >= 0:
        pieces.append(f"最近消息距今约 {facts['age']:.3f} s")
    elif facts["last_msg_time"]:
        pieces.append(f"最后消息时间 {facts['last_msg_time']}")
    return "，".join(pieces) + "。"


def _unavailable(
    *,
    call_id: str,
    params: ToolParams,
    tool: Tool | None,
    error: str,
    summary: str,
) -> ToolExecuteResult:
    return build_tool_result(
        call_id=call_id,
        tool_name="topic_monitor",
        success=False,
        status="unavailable",
        facts={"reason": error, "params": _public_params(params)},
        summary=summary,
        error=error,
        data={
            "params": _public_params(params),
            "input_schema": schema_to_payload(tool.input_schema) if tool else {},
            "output_schema": schema_to_payload(tool.output_schema) if tool else {},
            "result_schema": dict(tool.result_schema) if tool else {},
        },
        raw_output="",
    )


def _public_params(params: ToolParams) -> dict[str, object]:
    return {key: value for key, value in params.items() if not str(key).startswith("_")}
