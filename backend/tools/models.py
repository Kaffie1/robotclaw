from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from backend.shared import next_tool_call_id


class FieldType(str, Enum):
    kInt = "int"
    kBool = "bool"
    kDouble = "double"
    kString = "string"
    kTimestamp = "timestamp"


@dataclass
class FieldSchema:
    type: FieldType
    description: str = ""
    unit: str = ""


ToolSchema = dict[str, FieldSchema]
ToolJsonSchema = dict[str, Any]
ToolParams = dict[str, Any]
ToolExecuteResult = dict[str, Any]
ToolExecute = Callable[[ToolParams], ToolExecuteResult]
ToolCall = dict[str, Any]
ToolResult = dict[str, Any]
TOOL_RESULT_STATUS_VALUES = ("completed", "failed", "blocked", "unavailable", "rejected")


@dataclass
class Tool:
    name: str
    input_schema: ToolSchema = field(default_factory=dict)
    output_schema: ToolSchema = field(default_factory=dict)
    result_schema: ToolJsonSchema = field(default_factory=dict)
    execute: ToolExecute | None = None


def build_field_schema(
    field_type: FieldType,
    *,
    description: str = "",
    unit: str = "",
) -> FieldSchema:
    return FieldSchema(type=field_type, description=description, unit=unit)


def build_tool_call(
    tool_name: str,
    *,
    params: dict[str, Any] | None = None,
    session_id: str = "",
    task_id: str = "",
    call_id: str | None = None,
) -> ToolCall:
    return {
        "tool_name": str(tool_name or "").strip(),
        "params": dict(params or {}),
        "call_id": str(call_id or next_tool_call_id()).strip(),
        "session_id": str(session_id or "").strip(),
        "task_id": str(task_id or "").strip(),
    }


def build_tool_result(
    *,
    tool_name: str,
    success: bool,
    status: str,
    call_id: str = "",
    facts: dict[str, Any] | None = None,
    summary: str = "",
    data: dict[str, Any] | None = None,
    error: str = "",
    raw_output: str = "",
) -> ToolResult:
    return {
        "call_id": str(call_id or "").strip(),
        "tool_name": str(tool_name or "").strip(),
        "success": bool(success),
        "status": str(status or "").strip(),
        "facts": dict(facts or {}),
        "summary": str(summary or "").strip(),
        "data": dict(data or {}),
        "error": str(error or "").strip(),
        "raw_output": str(raw_output or ""),
    }


def tool_to_definition(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "input_schema": schema_to_payload(tool.input_schema),
        "output_schema": schema_to_payload(tool.output_schema),
        "result_schema": dict(tool.result_schema or build_tool_result_schema(tool.output_schema)),
    }


def schema_to_payload(schema: ToolSchema) -> dict[str, Any]:
    return {
        name: {
            "type": field.type.value,
            "description": field.description,
            "unit": field.unit,
        }
        for name, field in schema.items()
    }


def schema_to_json_properties(schema: ToolSchema) -> dict[str, Any]:
    return {
        name: _field_schema_to_json_schema(field)
        for name, field in schema.items()
    }


def build_tool_result_schema(output_schema: ToolSchema | None = None) -> ToolJsonSchema:
    output_properties = schema_to_json_properties(output_schema or {})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "call_id",
            "tool_name",
            "success",
            "status",
            "facts",
            "summary",
            "data",
            "error",
            "raw_output",
        ],
        "properties": {
            "call_id": {
                "type": "string",
                "description": "对应的工具调用 ID。",
            },
            "tool_name": {
                "type": "string",
                "description": "工具名称。",
            },
            "success": {
                "type": "boolean",
                "description": "工具执行是否成功。",
            },
            "status": {
                "type": "string",
                "enum": list(TOOL_RESULT_STATUS_VALUES),
                "description": "工具执行状态。completed 表示执行完成，failed 表示执行失败，blocked 表示被权限或连接条件阻断，unavailable 表示执行器不可用，rejected 表示计划阶段被拒绝。",
            },
            "facts": {
                "type": "object",
                "description": "面向规则和后续流程的结构化事实。",
                "additionalProperties": True,
            },
            "summary": {
                "type": "string",
                "description": "给 LLM 或前端展示的简短摘要。",
            },
            "data": {
                "type": "object",
                "description": "补充结构化载荷，业务输出统一放在 data.output。",
                "additionalProperties": True,
                "properties": {
                    "params": {
                        "type": "object",
                        "description": "本次工具调用的公开参数。",
                        "additionalProperties": True,
                    },
                    "output": {
                        "type": "object",
                        "description": "工具业务输出，字段结构由 output_schema 定义。",
                        "additionalProperties": not bool(output_properties),
                        "properties": output_properties,
                    },
                    "input_schema": {
                        "type": "object",
                        "description": "工具输入 schema 的序列化结果。",
                        "additionalProperties": True,
                    },
                    "output_schema": {
                        "type": "object",
                        "description": "工具输出 schema 的序列化结果。",
                        "additionalProperties": True,
                    },
                    "result_schema": {
                        "type": "object",
                        "description": "统一 ToolResult schema 的序列化结果。",
                        "additionalProperties": True,
                    },
                    "request_payload": {
                        "type": "string",
                        "description": "序列化后的远程 service 请求体。",
                    },
                },
            },
            "error": {
                "type": "string",
                "description": "错误码或错误摘要；成功时通常为空字符串。",
            },
            "raw_output": {
                "type": "string",
                "description": "保留的原始文本输出，优先使用 stdout，否则回退到 stderr。",
            },
        },
    }


def get_tool_result_output(result: ToolResult) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if not isinstance(data, dict):
        return {}
    output = data.get("output")
    return dict(output) if isinstance(output, dict) else {}


def _field_schema_to_json_schema(field: FieldSchema) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": _json_type_for_field(field.type),
    }
    if field.description:
        schema["description"] = field.description
    if field.unit:
        schema["unit"] = field.unit
    if field.type == FieldType.kTimestamp:
        schema["format"] = "date-time"
    return schema


def _json_type_for_field(field_type: FieldType) -> str:
    mapping = {
        FieldType.kInt: "integer",
        FieldType.kBool: "boolean",
        FieldType.kDouble: "number",
        FieldType.kString: "string",
        FieldType.kTimestamp: "string",
    }
    return mapping[field_type]
