from __future__ import annotations

from typing import Any, Protocol

from backend.llm.config import LLMConfig, load_llm_config
from backend.llm.models import LLMMessage, LLMRequest, LLMResponse, StructuredLLMResponse
from backend.llm.parser import extract_json_object, to_payload


class LLMBackend(Protocol):
    def invoke(self, request: LLMRequest) -> LLMResponse: ...


class MockLLMBackend:
    def invoke(self, request: LLMRequest) -> LLMResponse:
        last_message = request.messages[-1].content if request.messages else ""
        content = self._build_mock_response(last_message)
        return LLMResponse(
            model=request.model,
            content=content,
            finish_reason="stop",
            raw={"provider": "mock"},
        )

    def _build_mock_response(self, prompt: str) -> str:
        normalized = prompt.strip()
        if "总结" in normalized or "summary" in normalized.lower():
            return '{"summary":"已根据当前证据生成诊断总结。","evidence":["已完成问题理解","已完成基础工具规划"],"next_steps":["继续连接机器人并采集事实"]}'
        if "route" in normalized.lower() or "playbook" in normalized.lower():
            if any(keyword in normalized for keyword in ("雷达", "scan", "lidar")):
                return '{"route":"playbook","reason":"问题包含雷达关键词，优先走经验流程。","matched_playbook_id":"lidar-no-data"}'
            return '{"route":"knowledge","reason":"未命中固定经验流程，进入知识检索路径。","matched_playbook_id":""}'
        if "分类" in normalized or "category" in normalized.lower():
            if any(keyword in normalized for keyword in ("雷达", "scan", "lidar")):
                return '{"category":"lidar","summary":"识别为传感器/雷达异常问题","detail":"问题包含雷达或扫描数据关键词。"}'
            if any(keyword in normalized for keyword in ("定位", "漂移", "localization", "amcl")):
                return '{"category":"localization","summary":"识别为定位异常问题","detail":"问题与定位缺失、漂移或定位质量下降相关。"}'
            if any(keyword in normalized for keyword in ("地图", "map", "加载失败")):
                return '{"category":"mapping","summary":"识别为地图/建图相关问题","detail":"问题包含地图加载或地图服务相关描述。"}'
            return '{"category":"general","summary":"识别为通用运维问答","detail":"当前先走通用聊天诊断链路。"}'
        if "tool" in normalized.lower() or "规划" in normalized:
            return '{"category":"general","tools":[{"tool_name":"check_nodes","reason":"先确认机器人节点运行状态"}],"summary":"先采集运行态事实"}'
        return '{"summary":"已生成默认总结。","evidence":[],"next_steps":["继续连接机器人并采集事实"]}'


class LLMClient:
    def __init__(self, config: LLMConfig | None = None, backend: LLMBackend | None = None) -> None:
        self.config = config or load_llm_config()
        self.backend = backend or self._build_backend(self.config)

    def invoke(
        self,
        *,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        request = LLMRequest(
            messages=messages,
            model=model or self.config.model,
            temperature=self.config.temperature if temperature is None else temperature,
            max_tokens=self.config.max_tokens if max_tokens is None else max_tokens,
            metadata=dict(metadata or {}),
        )
        return self.backend.invoke(request)

    def invoke_text(
        self,
        *,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        messages: list[LLMMessage] = []
        if system_prompt.strip():
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))
        return self.invoke(messages=messages, model=model, metadata=metadata)

    def invoke_structured(
        self,
        *,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StructuredLLMResponse:
        response = self.invoke_text(prompt=prompt, system_prompt=system_prompt, model=model, metadata=metadata)
        payload = extract_json_object(response.content)
        return StructuredLLMResponse(
            model=response.model,
            content=response.content,
            parsed=payload,
            finish_reason=response.finish_reason,
            raw=response.raw,
        )

    def invoke_schema(
        self,
        *,
        prompt: str,
        schema_parser,
        system_prompt: str = "",
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StructuredLLMResponse:
        response = self.invoke_structured(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            metadata=metadata,
        )
        parsed = schema_parser(response.parsed)
        return StructuredLLMResponse(
            model=response.model,
            content=response.content,
            parsed=to_payload(parsed),
            finish_reason=response.finish_reason,
            raw=response.raw,
        )

    def _build_backend(self, config: LLMConfig) -> LLMBackend:
        if config.provider == "mock":
            return MockLLMBackend()
        return MockLLMBackend()
