from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import uuid
from urllib import error, request
from typing import Any, Protocol

from backend.llm.config import LLMConfig, load_llm_config
from backend.llm.models import AudioTranscriptionResponse, LLMMessage, LLMRequest, LLMResponse, StructuredLLMResponse
from backend.llm.parser import extract_json_object, to_payload
from backend.llm.volc_asr import load_volc_asr_config, transcribe_audio_bytes
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

    def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        mime_type: str = "audio/webm",
        language: str | None = None,
        model: str | None = None,
        prompt: str = "",
    ) -> AudioTranscriptionResponse:
        if not audio_bytes:
            raise ValueError("audio_bytes 不能为空")
        if self.config.asr_provider == "volcengine":
            response = asyncio.run(
                transcribe_audio_bytes(
                    audio_bytes=audio_bytes,
                    mime_type=mime_type,
                    filename=filename,
                    config=load_volc_asr_config(),
                    language=language,
                )
            )
            return AudioTranscriptionResponse(
                model=str(response.get("model", "bigmodel")),
                text=str(response.get("text", "")).strip(),
                raw=dict(response.get("raw", {}) or {}),
            )
        if self.config.asr_provider not in {"openai", "openai_compatible"}:
            raise ValueError(f"不支持的 ASR provider: {self.config.asr_provider}")
        api_base = (self.config.api_base or "").rstrip("/")
        if not api_base:
            raise ValueError("openai provider 缺少 api_base 配置")
        if not self.config.api_key:
            raise ValueError("openai provider 缺少 api_key 配置")
        selected_model = (model or self.config.asr_model or "").strip()
        if not selected_model:
            raise ValueError("ASR 未配置 model")

        boundary = f"----RobotClawASR{uuid.uuid4().hex}"
        body = _build_multipart_form_data(
            boundary=boundary,
            fields={
                "model": selected_model,
                "language": (language or self.config.asr_language or "").strip(),
                "prompt": prompt.strip(),
                "response_format": "json",
            },
            file_field_name="file",
            filename=filename or _guess_filename(mime_type),
            file_bytes=audio_bytes,
            mime_type=mime_type or "application/octet-stream",
        )
        logger.info(
            "LLM transcribe input provider=%s profile_id=%s model=%s filename=%s mime_type=%s bytes=%s",
            self.config.provider,
            self.config.profile_id,
            selected_model,
            filename,
            mime_type,
            len(audio_bytes),
        )
        req = request.Request(
            api_base + "/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.config.asr_timeout_seconds) as response:
                raw_bytes = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.warning("LLM transcribe HTTP error code=%s detail=%s", exc.code, detail[:300])
            raise ValueError("ASR 接口调用失败") from exc
        except error.URLError as exc:
            logger.warning("LLM transcribe network error reason=%s", exc.reason)
            raise ValueError("ASR 接口不可达，请检查网络或 api_base 配置") from exc

        payload = json.loads(raw_bytes.decode("utf-8"))
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError("ASR 接口未返回 text")
        logger.info(
            "LLM transcribe output provider=%s profile_id=%s model=%s text=%s",
            self.config.provider,
            self.config.profile_id,
            selected_model,
            _clip_text(text),
        )
        return AudioTranscriptionResponse(model=selected_model, text=text, raw=payload)

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
        content = _to_langchain_content(message.content)
        if message.role == "system":
            converted.append(SystemMessage(content=content))
        elif message.role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _to_langchain_content(content: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    if not isinstance(content, list):
        return content

    converted: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            converted.append({"type": "text", "text": str(block)})
            continue
        block_type = str(block.get("type") or "").strip().lower()
        if block_type == "image":
            source = block.get("source") if isinstance(block.get("source"), dict) else {}
            media_type = str(source.get("media_type") or block.get("media_type") or "image/png").strip() or "image/png"
            data = str(source.get("data") or block.get("data") or "").strip()
            if data:
                converted.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    }
                )
            continue
        converted.append({"type": "text", "text": str(block.get("text", ""))})
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
            "content": _clip_text(_content_to_log_text(message.content), limit=160),
        }
        for message in messages
    ]


def _content_to_log_text(content: str | list[dict[str, Any]]) -> str:
    if not isinstance(content, list):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image":
            source = block.get("source") if isinstance(block.get("source"), dict) else {}
            parts.append(f"[image:{source.get('media_type', 'image')}]")
        elif isinstance(block, dict):
            parts.append(str(block.get("text", "")))
        else:
            parts.append(str(block))
    return " ".join(item for item in parts if item).strip()


def _build_multipart_form_data(
    *,
    boundary: str,
    fields: dict[str, str],
    file_field_name: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
) -> bytes:
    body = bytearray()
    for key, value in fields.items():
        if not str(value or "").strip():
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field_name}"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body)


def _guess_filename(mime_type: str) -> str:
    guessed_extension = mimetypes.guess_extension(mime_type or "") or ".bin"
    return f"audio{guessed_extension}"
