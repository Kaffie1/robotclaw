from __future__ import annotations

from typing import Any

from ..core.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_CHAT_MODEL,
    OPENAI_CHAT_TEMPERATURE,
    OPENAI_ENABLE_REASONING_SPLIT,
    OPENAI_THINK,
)
from ..core.models import ApiError


def load_chat_message_classes() -> tuple[Any, Any, Any]:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except Exception as exc:  # noqa: BLE001
        raise ApiError("聊天依赖未安装，请先安装 langchain-openai 和 openai") from exc
    return AIMessage, HumanMessage, SystemMessage


def _build_extra_body() -> dict[str, Any]:
    return {
        "reasoning_split": OPENAI_ENABLE_REASONING_SPLIT,
        "think": OPENAI_THINK,
    }


def _normalize_model_exception_message(exc: Exception, *, model: str) -> str:
    raw_message = str(exc or "").strip()
    lowered = raw_message.lower()
    provider_label = OPENAI_BASE_URL or "默认模型服务"
    if "account_expired" in lowered:
        return (
            f"聊天模型服务账号已过期，请检查 `.env` 中的 OPENAI_API_KEY 是否仍有效，"
            f"或确认 OPENAI_BASE_URL={provider_label} 对应账户状态正常。当前模型: {model}"
        )
    if "invalid_api_key" in lowered or "incorrect api key" in lowered or "unauthorized" in lowered:
        return (
            f"聊天模型认证失败，请检查 `.env` 中的 OPENAI_API_KEY 和 OPENAI_BASE_URL 配置。"
            f"当前模型: {model}"
        )
    if "403" in lowered:
        return (
            f"聊天模型服务拒绝访问（403），请检查 OPENAI_API_KEY、账户状态或 OPENAI_BASE_URL 配置。"
            f"当前模型: {model}，服务地址: {provider_label}"
        )
    return raw_message or f"聊天模型调用失败: {model}"


def _create_chat_openai(*, temperature: float):
    if not OPENAI_API_KEY:
        raise ApiError("未配置 OPENAI_API_KEY，无法调用聊天模型")
    try:
        from langchain_openai import ChatOpenAI
    except Exception as exc:  # noqa: BLE001
        raise ApiError("聊天依赖未安装，请先安装 langchain-openai 和 openai") from exc
    return ChatOpenAI(
        model=OPENAI_CHAT_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=temperature,
        base_url=OPENAI_BASE_URL,
        extra_body=_build_extra_body(),
    )


def invoke_chat_model(llm: Any, payload: Any, *, model: str) -> Any:
    try:
        return llm.invoke(payload)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApiError(_normalize_model_exception_message(exc, model=model)) from exc


def build_chat_model():
    return _create_chat_openai(temperature=OPENAI_CHAT_TEMPERATURE)


def build_router_model():
    return _create_chat_openai(temperature=0)
