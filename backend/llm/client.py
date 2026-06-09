from __future__ import annotations

import json
import re
from typing import Any, Protocol

from backend.llm.config import LLMConfig, load_llm_config
from backend.llm.models import LLMMessage, LLMRequest, LLMResponse, StructuredLLMResponse
from backend.llm.parser import extract_json_object, to_payload
from backend.shared.config import OPENAI_ENABLE_REASONING_SPLIT, OPENAI_THINK
from backend.shared import get_logger


logger = get_logger("llm.client")


class LLMBackend(Protocol):
    def invoke(self, request: LLMRequest) -> LLMResponse: ...


class ChatOpenAIBackend:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._llm = self._create_llm()

    def invoke(self, request_payload: LLMRequest) -> LLMResponse:
        response = self._llm.invoke(_to_langchain_messages(request_payload.messages))
        message = _extract_langchain_message_content(response.content)
        finish_reason = str(getattr(response, "response_metadata", {}).get("finish_reason", "stop") or "stop")
        return LLMResponse(
            model=str(getattr(response, "response_metadata", {}).get("model_name", "") or self.config.model),
            content=message,
            finish_reason=finish_reason,
            raw=_build_raw_payload(response),
        )

    def _create_llm(self) -> Any:
        api_base = (self.config.api_base or "").rstrip("/")
        if not api_base:
            raise ValueError("openai provider 缺少 api_base 配置")
        if not self.config.api_key:
            raise ValueError("openai provider 缺少 api_key 配置")

        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise RuntimeError("聊天依赖未安装，请先安装 langchain-openai 和 openai") from exc

        return ChatOpenAI(
            model=self.config.model,
            api_key=self.config.api_key,
            base_url=api_base,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout_seconds,
            extra_body=_build_extra_body(),
        )


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
        llm_request = LLMRequest(
            messages=messages,
            model=model or self.config.model,
            temperature=self.config.temperature if temperature is None else temperature,
            max_tokens=self.config.max_tokens if max_tokens is None else max_tokens,
            metadata=dict(metadata or {}),
        )
        logger.info(
            "LLM invoke input provider=%s profile_id=%s model=%s temperature=%s max_tokens=%s metadata=%s messages=%s",
            self.config.provider,
            self.config.profile_id,
            llm_request.model,
            llm_request.temperature,
            llm_request.max_tokens,
            llm_request.metadata,
            _summarize_messages(llm_request.messages),
        )
        try:
            response = self.backend.invoke(llm_request)
        except Exception:
            logger.exception(
                "LLM invoke failed provider=%s profile_id=%s model=%s metadata=%s",
                self.config.provider,
                self.config.profile_id,
                llm_request.model,
                llm_request.metadata,
            )
            raise
        logger.info(
            "LLM invoke output provider=%s profile_id=%s model=%s finish_reason=%s content=%s",
            self.config.provider,
            self.config.profile_id,
            response.model,
            response.finish_reason,
            _clip_text(response.content),
        )
        return response

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
        logger.info(
            "LLM structured output model=%s parsed_keys=%s",
            response.model,
            sorted(payload.keys()),
        )
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
        logger.info(
            "LLM schema output model=%s parsed=%s",
            response.model,
            _clip_text(json.dumps(to_payload(parsed), ensure_ascii=False)),
        )
        return StructuredLLMResponse(
            model=response.model,
            content=response.content,
            parsed=to_payload(parsed),
            finish_reason=response.finish_reason,
            raw=response.raw,
        )

    def _build_backend(self, config: LLMConfig) -> LLMBackend:
        if config.provider in {"openai", "openai_compatible"}:
            return ChatOpenAIBackend(config)
        raise ValueError(f"不支持的 LLM provider: {config.provider}")


def _to_langchain_messages(messages: list[LLMMessage]) -> list[Any]:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except Exception as exc:
        raise RuntimeError("聊天依赖未安装，请先安装 langchain-openai 和 openai") from exc

    converted: list[Any] = []
    for message in messages:
        if message.role == "system":
            converted.append(SystemMessage(content=message.content))
        elif message.role == "assistant":
            converted.append(AIMessage(content=message.content))
        else:
            converted.append(HumanMessage(content=message.content))
    return converted


def _extract_langchain_message_content(content: Any) -> str:
    if isinstance(content, str):
        return _strip_think_blocks(content)
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                texts.append(item)
        merged = "".join(texts).strip()
        if merged:
            return _strip_think_blocks(merged)
    raise ValueError("LLM 返回缺少 message.content")


def _build_raw_payload(response: Any) -> dict[str, Any]:
    response_metadata = getattr(response, "response_metadata", {}) or {}
    usage_metadata = getattr(response, "usage_metadata", {}) or {}
    return {
        "content": response.content,
        "response_metadata": response_metadata,
        "usage_metadata": usage_metadata,
        "id": getattr(response, "id", ""),
    }


def _build_extra_body() -> dict[str, Any]:
    return {
        "reasoning_split": OPENAI_ENABLE_REASONING_SPLIT,
        "think": OPENAI_THINK,
    }


def _clip_text(text: str, limit: int = 240) -> str:
    normalized = " ".join((text or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


def _strip_think_blocks(text: str) -> str:
    normalized = text or ""
    cleaned = re.sub(r"<think>.*?</think>", "", normalized, flags=re.DOTALL | re.IGNORECASE).strip()
    return cleaned or normalized.strip()


def _summarize_messages(messages: list[LLMMessage]) -> list[dict[str, str]]:
    return [
        {
            "role": message.role,
            "content": _clip_text(message.content, limit=160),
        }
        for message in messages
    ]
