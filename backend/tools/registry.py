from __future__ import annotations

import json
from difflib import get_close_matches
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel

from ..core.models import ApiError
from ..common import get_fault_logger, get_fault_trace_logger
from .base import ToolDefinition
from .docker import (
    DockerComposeExecArgs,
    DockerComposeModuleArgs,
    handle_docker_compose_down_module,
    handle_docker_compose_exec_command,
    handle_docker_compose_up_module,
)
from .module import (
    ModuleHealthCheckArgs,
    ModuleInstallArgs,
    ModulePreparePackagesArgs,
    ModuleReplaceRemoteAssetsArgs,
    ModuleStagePackagesArgs,
    ModuleStartArgs,
    handle_module_health_check,
    handle_module_install,
    handle_module_prepare_packages,
    handle_module_replace_remote_assets,
    handle_module_stage_packages,
    handle_module_start,
)

from .package import (
    PackageInstallArgs,
    PackagePrepareSourceArgs,
    PackageProbeMachineTypesArgs,
    PackageStageRemoteArgs,
    handle_package_install,
    handle_package_prepare_source,
    handle_package_probe_credentials,
    handle_package_probe_machine_types,
    handle_package_stage_remote,
)

from .remote import (
    DeviceTypeArgs,
    PingHostArgs,
    RemoteCommandArgs,
    RemoteEnvironmentVariableArgs,
    RemoteExecuteArgs,
    RemoteFileTransferArgs,
    RemotePathPrefixArgs,
    RemotePathArgs,
    RemoteScanPathsArgs,
    handle_remote_execute_readonly,
    handle_remote_execute_command,
    handle_remote_ensure_executable,
    handle_ping_host,
    handle_remote_backup_path,
    handle_remote_get_file_owner,
    handle_remote_get_interactive_env,
    handle_remote_list_dir,
    handle_remote_read_file,
    handle_remote_remove_files_by_prefix,
    handle_remote_restore_backup,
    handle_remote_path_exists,
    handle_remote_resolve_path,
    handle_remote_scan_paths,
    handle_remote_shortcuts,
)
from .ros import (
    RosComposeExecArgs,
    RosNameArgs,
    RosServiceCallArgs,
    RosTypeNameArgs,
    handle_ros_list_services,
    handle_ros_list_topics,
    handle_ros_message_definition,
    handle_ros_service_call,
    handle_ros_service_definition,
    handle_ros_service_info,
    handle_ros_service_type,
    handle_ros_compose_exec_command,
    handle_ros_topic_echo,
    handle_ros_topic_info,
    handle_ros_topic_type,
)

logger = get_fault_logger()
trace_logger = get_fault_trace_logger()


def _truncate_trace_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, dict):
        normalized_keys = {str(key) for key in value.keys()}
        if normalized_keys and normalized_keys <= {"label", "value"}:
            items: dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(item, str):
                    items[str(key)] = item if len(item) <= 200 else f"{item[:200]}…(truncated,{len(item)} chars)"
                else:
                    items[str(key)] = _truncate_trace_value(item, depth=depth + 1)
            return items
    if depth >= 4:
        return "…"
    if isinstance(value, dict):
        items: dict[str, Any] = {}
        for key, item in list(value.items())[:60]:
            items[str(key)] = _truncate_trace_value(item, depth=depth + 1)
        return items
    if isinstance(value, list):
        return [_truncate_trace_value(item, depth=depth + 1) for item in value[:60]]
    if isinstance(value, str):
        if len(value) <= 4000:
            return value
        return f"{value[:4000]}…(truncated,{len(value)} chars)"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def append_tool_trace(event: str, payload: dict[str, Any]) -> None:
    trace_logger.info(
        json.dumps(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                "payload": _truncate_trace_value(payload),
            },
            ensure_ascii=False,
        )
    )


def _summarize_tool_result(result: Any) -> dict[str, Any]:
    """对工具执行结果进行总结和提炼，提取关键字段和信息，构建一个简洁的摘要用于日志记录和分析"""
    if not isinstance(result, dict):
        return {"result_type": type(result).__name__}

    summary: dict[str, Any] = {}

    for key in ("device_type", "warning", "output", "command", "resolved_path", "resolved_remote_path"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            summary[key] = value.strip()

    machine_options = result.get("machine_options")
    if isinstance(machine_options, list):
        summary["machine_option_count"] = len(machine_options)
        summary["machine_option_values"] = [
            str(item.get("value") or "").strip()
            for item in machine_options[:20]
            if isinstance(item, dict) and str(item.get("value") or "").strip()
        ]

    removed_files = result.get("removed_files")
    if isinstance(removed_files, list):
        summary["removed_file_count"] = len(removed_files)

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        summary["exit_code"] = nested_result.get("exit_code")
        stdout = nested_result.get("stdout")
        stderr = nested_result.get("stderr")
        if isinstance(stdout, str) and stdout.strip():
            summary["stdout_preview"] = stdout.strip()
        if isinstance(stderr, str) and stderr.strip():
            summary["stderr_preview"] = stderr.strip()

    return summary


class EmptyArgs(BaseModel):
    pass


def _build_ros_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="ros_list_topics",
            description="列出当前 ROS 环境中的所有 topic。",
            args_schema=EmptyArgs,
            handler=handle_ros_list_topics,
            module="ros",
        ),
        ToolDefinition(
            name="ros_list_services",
            description="列出当前 ROS 环境中的所有 service。",
            args_schema=EmptyArgs,
            handler=handle_ros_list_services,
            module="ros",
        ),
        ToolDefinition(
            name="ros_topic_info",
            description="查看指定 topic 的连接信息、发布者和订阅者。",
            args_schema=RosNameArgs,
            handler=handle_ros_topic_info,
            module="ros",
            aliases=("ros_get_topic_info",),
        ),
        ToolDefinition(
            name="ros_topic_type",
            description="查看指定 topic 的消息类型。",
            args_schema=RosNameArgs,
            handler=handle_ros_topic_type,
            module="ros",
            aliases=("ros_get_topic_type",),
        ),
        ToolDefinition(
            name="ros_message_definition",
            description="查看 ROS 消息类型定义，并尽量展开嵌套字段。",
            args_schema=RosTypeNameArgs,
            handler=handle_ros_message_definition,
            module="ros",
            aliases=("ros_get_message_definition",),
        ),
        ToolDefinition(
            name="ros_topic_echo",
            description="抓取一次 topic 样本消息，用于现场排查。",
            args_schema=RosNameArgs,
            handler=handle_ros_topic_echo,
            module="ros",
        ),
        ToolDefinition(
            name="ros_service_info",
            description="查看指定 service 的连接和节点信息。",
            args_schema=RosNameArgs,
            handler=handle_ros_service_info,
            module="ros",
            aliases=("ros_get_service_info",),
        ),
        ToolDefinition(
            name="ros_service_type",
            description="查看指定 service 的服务类型。",
            args_schema=RosNameArgs,
            handler=handle_ros_service_type,
            module="ros",
            aliases=("ros_get_service_type",),
        ),
        ToolDefinition(
            name="ros_service_definition",
            description="查看 ROS 服务类型定义，并尽量展开嵌套字段。",
            args_schema=RosTypeNameArgs,
            handler=handle_ros_service_definition,
            module="ros",
            aliases=("ros_get_service_definition",),
        ),
        ToolDefinition(
            name="ros_service_call",
            description="调用指定 ROS service，并返回执行结果。",
            args_schema=RosServiceCallArgs,
            handler=handle_ros_service_call,
            module="ros",
            aliases=("ros_call_service",),
        ),
        ToolDefinition(
            name="ros_compose_exec_command",
            description="在 ROS compose 场景下进入指定服务容器执行命令，默认服务为 rosbridge。",
            args_schema=RosComposeExecArgs,
            handler=handle_ros_compose_exec_command,
            module="ros",
            aliases=("ros_compose_exec",),
        ),
    ]


def _build_docker_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="docker_compose_down_module",
            description="停止单个 docker compose 模块服务。",
            args_schema=DockerComposeModuleArgs,
            handler=handle_docker_compose_down_module,
            module="docker",
        ),
        ToolDefinition(
            name="docker_compose_up_module",
            description="启动单个 docker compose 模块服务，并默认等待一段时间让容器稳定。",
            args_schema=DockerComposeModuleArgs,
            handler=handle_docker_compose_up_module,
            module="docker",
        ),
        ToolDefinition(
            name="docker_compose_exec_command",
            description="在指定 docker compose 项目和服务容器内执行命令。",
            args_schema=DockerComposeExecArgs,
            handler=handle_docker_compose_exec_command,
            module="docker",
            aliases=("docker_compose_exec",),
        ),
    ]


def _build_remote_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="ping_host",
            description="从当前机器人侧 ping 指定主机，用于确认网络通信是否正常。",
            args_schema=PingHostArgs,
            handler=handle_ping_host,
            module="remote",
        ),
        ToolDefinition(
            name="remote_resolve_path",
            description="解析远端路径并返回是否存在，可选择 ORIN 或 PICO。",
            args_schema=RemotePathArgs,
            handler=handle_remote_resolve_path,
            module="remote",
        ),
        ToolDefinition(
            name="remote_path_exists",
            description="检查远端路径是否存在，并判断是否是目录。",
            args_schema=RemotePathArgs,
            handler=handle_remote_path_exists,
            module="remote",
        ),
        ToolDefinition(
            name="remote_list_dir",
            description="列出远端目录内容，可选择 ORIN 或 PICO。",
            args_schema=RemotePathArgs,
            handler=handle_remote_list_dir,
            module="remote",
        ),
        ToolDefinition(
            name="remote_scan_paths",
            description="递归扫描远端路径，并按关键字筛选路径和目录。",
            args_schema=RemoteScanPathsArgs,
            handler=handle_remote_scan_paths,
            module="remote",
        ),
        ToolDefinition(
            name="remote_shortcuts",
            description="获取远端常用目录快捷入口。",
            args_schema=DeviceTypeArgs,
            handler=handle_remote_shortcuts,
            module="remote",
        ),
        ToolDefinition(
            name="remote_execute_readonly",
            description="在远端执行只读诊断命令，禁止修改环境。",
            args_schema=RemoteExecuteArgs,
            handler=handle_remote_execute_readonly,
            module="remote",
            aliases=("remote_exec_readonly",),
        ),
        ToolDefinition(
            name="remote_execute_command",
            description="在远端执行带副作用的维护命令，适合部署、修复和人工维护场景。",
            args_schema=RemoteCommandArgs,
            handler=handle_remote_execute_command,
            module="remote",
            aliases=("remote_exec_command",),
        ),
        ToolDefinition(
            name="remote_get_interactive_env",
            description="读取远端交互式 shell 环境变量。",
            args_schema=RemoteEnvironmentVariableArgs,
            handler=handle_remote_get_interactive_env,
            module="remote",
        ),
        ToolDefinition(
            name="remote_ensure_executable",
            description="确保远端文件具备可执行权限。",
            args_schema=RemotePathArgs,
            handler=handle_remote_ensure_executable,
            module="remote",
        ),
        ToolDefinition(
            name="remote_read_file",
            description="读取远端文本文件内容。",
            args_schema=RemotePathArgs,
            handler=handle_remote_read_file,
            module="remote",
        ),
        ToolDefinition(
            name="remote_get_file_owner",
            description="读取远端文件所有者。",
            args_schema=RemotePathArgs,
            handler=handle_remote_get_file_owner,
            module="remote",
        ),
        ToolDefinition(
            name="remote_backup_path",
            description="为远端文件或目录创建备份副本。",
            args_schema=RemotePathArgs,
            handler=handle_remote_backup_path,
            module="remote",
        ),
        ToolDefinition(
            name="remote_restore_backup",
            description="将远端备份恢复到目标路径。",
            args_schema=RemoteFileTransferArgs,
            handler=handle_remote_restore_backup,
            module="remote",
        ),
        ToolDefinition(
            name="remote_remove_files_by_prefix",
            description="按前缀清理远端目录中的旧文件。",
            args_schema=RemotePathPrefixArgs,
            handler=handle_remote_remove_files_by_prefix,
            module="remote",
        ),
    ]


def _build_package_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="package_probe_credentials",
            description="探测部署包是否支持 --user / --password 参数。",
            args_schema=RemotePathArgs,
            handler=handle_package_probe_credentials,
            module="package",
        ),
        ToolDefinition(
            name="package_prepare_source",
            description="准备整包部署安装包来源，解析本地临时文件或从文件服务器下载到本机。",
            args_schema=PackagePrepareSourceArgs,
            handler=handle_package_prepare_source,
            module="package",
        ),
        ToolDefinition(
            name="package_install",
            description="执行整包安装命令，并根据部署包能力自动处理目标用户名和密码参数。",
            args_schema=PackageInstallArgs,
            handler=handle_package_install,
            module="package",
        ),
        ToolDefinition(
            name="package_probe_machine_types",
            description="执行整包安装包的机型探测命令，并返回可选机型列表，失败时回退到默认机型列表。",
            args_schema=PackageProbeMachineTypesArgs,
            handler=handle_package_probe_machine_types,
            module="package",
        ),
        ToolDefinition(
            name="package_stage_remote",
            description="在目标处理器上复用或上传整包安装包，并按需清理旧包。",
            args_schema=PackageStageRemoteArgs,
            handler=handle_package_stage_remote,
            module="package",
        ),
    ]


def _build_module_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="module_prepare_packages",
            description="准备模块部署安装包来源，解析本地临时文件或从文件服务器下载到本机。",
            args_schema=ModulePreparePackagesArgs,
            handler=handle_module_prepare_packages,
            module="module",
        ),
        ToolDefinition(
            name="module_replace_remote_assets",
            description="自动模块部署时替换远端 config、containers 与 docker-compose 片段。",
            args_schema=ModuleReplaceRemoteAssetsArgs,
            handler=handle_module_replace_remote_assets,
            module="module",
        ),
        ToolDefinition(
            name="module_stage_packages",
            description="清理旧模块包并上传新的模块安装包到目标目录。",
            args_schema=ModuleStagePackagesArgs,
            handler=handle_module_stage_packages,
            module="module",
        ),
        ToolDefinition(
            name="module_install",
            description="执行模块安装命令。",
            args_schema=ModuleInstallArgs,
            handler=handle_module_install,
            module="module",
        ),
        ToolDefinition(
            name="module_start",
            description="按需等待并执行模块启动命令。",
            args_schema=ModuleStartArgs,
            handler=handle_module_start,
            module="module",
        ),
        ToolDefinition(
            name="module_health_check",
            description="执行模块健康检查，并在启用时自动回滚。",
            args_schema=ModuleHealthCheckArgs,
            handler=handle_module_health_check,
            module="module",
        ),
    ]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions = [
            *_build_ros_tool_definitions(),
            *_build_docker_tool_definitions(),
            *_build_remote_tool_definitions(),
            *_build_package_tool_definitions(),
            *_build_module_tool_definitions(),
        ]
        self._by_name: dict[str, ToolDefinition] = {}
        for item in self._definitions:
            for candidate_name in (item.name, *item.aliases):
                normalized_name = str(candidate_name or "").strip()
                if not normalized_name:
                    continue
                existing = self._by_name.get(normalized_name)
                if existing is not None and existing.name != item.name:
                    raise RuntimeError(f"工具名称或别名冲突: {normalized_name}")
                self._by_name[normalized_name] = item

    def list_definitions(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for definition in self._definitions:
            items.append(
                {
                    "name": definition.name,
                    "module": definition.module,
                    "description": definition.description,
                    "aliases": list(definition.aliases),
                    "input_schema": definition.args_schema.model_json_schema(),
                }
            )
        return items

    def _suggest_tool_names(self, name: str) -> list[str]:
        candidate_names = sorted(self._by_name)
        return get_close_matches(str(name or "").strip(), candidate_names, n=5, cutoff=0.45)

    def call_tool(self, name: str, arguments: dict[str, Any] | None, tool_context: dict[str, Any] | None = None) -> dict[str, Any]:
        requested_name = str(name or "").strip()
        definition = self._by_name.get(requested_name)
        if definition is None:
            suggestions = self._suggest_tool_names(requested_name)
            payload = {"requested_name": requested_name}
            if suggestions:
                payload["suggestions"] = suggestions
                raise ApiError(
                    f"未找到工具: {requested_name}，你可以尝试: {', '.join(suggestions)}",
                    payload=payload,
                )
            raise ApiError(f"未找到工具: {requested_name}", payload=payload)
        payload = definition.args_schema.model_validate(arguments or {})
        logger.info("工具调用 | tool=%s | requested=%s", definition.name, requested_name)
        append_tool_trace(
            "tool_registry_call_start",
            {
                "requested_name": requested_name,
                "tool_name": definition.name,
                "arguments": arguments or {},
            },
        )
        result = definition.handler(payload, tool_context)
        append_tool_trace(
            "tool_registry_call_end",
            {
                "result_summary": _summarize_tool_result(result),
            },
        )
        return result

    def build_langchain_tools(self, tool_context: dict[str, Any] | None = None) -> list[Any]:
        from langchain_core.tools import StructuredTool

        tools = []
        for definition in self._definitions:
            def make_tool_handler(current_name: str) -> Callable[..., str]:
                def tool_handler(**kwargs: Any) -> str:
                    result = self.call_tool(current_name, kwargs, tool_context)
                    return json.dumps(result, ensure_ascii=False)

                return tool_handler

            tools.append(
                StructuredTool.from_function(
                    func=make_tool_handler(definition.name),
                    name=definition.name,
                    description=definition.description,
                    args_schema=definition.args_schema,
                )
            )
        return tools


tool_registry = ToolRegistry()
