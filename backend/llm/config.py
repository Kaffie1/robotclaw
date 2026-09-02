from __future__ import annotations

import json
from dataclasses import dataclass

from backend.shared.config import (
    LLM_ACTIVE_PROFILE,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_ASR_LANGUAGE,
    LLM_ASR_MODEL,
    LLM_ASR_PROVIDER,
    LLM_ASR_TIMEOUT,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_PROFILES,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    LLM_TIMEOUT,
    OPENAI_API_KEY,
    OPENAI_ASR_MODEL,
    OPENAI_BASE_URL,
    OPENAI_CHAT_MODEL,
    VOLCENGINE_ASR_ACCESS_KEY,
    VOLCENGINE_ASR_API_KEY,
    VOLCENGINE_ASR_WS_URL,
)


@dataclass(frozen=True)
class LLMConfig:
    profile_id: str = "default"
    label: str = "Default"
    provider: str = "openai"
    model: str = ""
    asr_provider: str = "openai"
    asr_model: str = ""
    asr_language: str = "zh"
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    asr_timeout_seconds: float = 60.0
    api_base: str = ""
    api_key: str = ""


def load_llm_config() -> LLMConfig:
    return LLMConfig(
        profile_id="default",
        label="Default",
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        asr_provider=_default_asr_provider(),
        asr_model=LLM_ASR_MODEL or OPENAI_ASR_MODEL,
        asr_language=LLM_ASR_LANGUAGE,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        timeout_seconds=LLM_TIMEOUT,
        asr_timeout_seconds=LLM_ASR_TIMEOUT,
        api_base=LLM_API_BASE,
        api_key=LLM_API_KEY,
    )


def load_llm_profiles() -> tuple[dict[str, LLMConfig], str]:
    raw_profiles = LLM_PROFILES
    active_profile_id = LLM_ACTIVE_PROFILE
    profiles: dict[str, LLMConfig] = {}

    if raw_profiles:
        payload = json.loads(raw_profiles)
        if not isinstance(payload, list):
            raise ValueError("LLM_PROFILES must be a JSON array")
        for item in payload:
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("profile_id", "")).strip()
            if not profile_id:
                continue
            profiles[profile_id] = LLMConfig(
                profile_id=profile_id,
                label=str(item.get("label", profile_id)).strip() or profile_id,
                provider=str(item.get("provider", "openai")).strip() or "openai",
                model=str(item.get("model", "")).strip(),
                asr_provider=str(item.get("asr_provider", "openai")).strip() or "openai",
                asr_model=str(item.get("asr_model", "")).strip(),
                asr_language=str(item.get("asr_language", "zh")).strip() or "zh",
                temperature=float(item.get("temperature", 0.0) or 0.0),
                max_tokens=int(item.get("max_tokens", 1024) or 1024),
                timeout_seconds=float(item.get("timeout_seconds", 30.0) or 30.0),
                asr_timeout_seconds=float(item.get("asr_timeout_seconds", 60.0) or 60.0),
                api_base=str(item.get("api_base", "")).strip(),
                api_key=str(item.get("api_key", "")).strip(),
            )

    if not profiles:
        default_config = load_llm_config()
        profiles[default_config.profile_id] = default_config

        openai_model = OPENAI_CHAT_MODEL
        openai_asr_model = OPENAI_ASR_MODEL
        openai_base = OPENAI_BASE_URL
        openai_key = OPENAI_API_KEY
        if openai_model:
            profiles["openai"] = LLMConfig(
                profile_id="openai",
                label="OpenAI-Compatible",
                provider="openai",
                model=openai_model,
                asr_provider=default_config.asr_provider,
                asr_model=openai_asr_model,
                asr_language=default_config.asr_language,
                temperature=default_config.temperature,
                max_tokens=default_config.max_tokens,
                timeout_seconds=default_config.timeout_seconds,
                asr_timeout_seconds=default_config.asr_timeout_seconds,
                api_base=openai_base,
                api_key=openai_key,
            )

    if active_profile_id not in profiles:
        active_profile_id = next(iter(profiles))
    return profiles, active_profile_id


def llm_config_from_payload(payload: dict) -> LLMConfig:
    profile_id = str(payload.get("profile_id", "")).strip()
    if not profile_id:
        raise ValueError("profile_id 不能为空")
    return LLMConfig(
        profile_id=profile_id,
        label=str(payload.get("label", profile_id)).strip() or profile_id,
        provider=str(payload.get("provider", "openai")).strip() or "openai",
        model=str(payload.get("model", "")).strip(),
        asr_provider=str(payload.get("asr_provider", "openai")).strip() or "openai",
        asr_model=str(payload.get("asr_model", "")).strip(),
        asr_language=str(payload.get("asr_language", "zh")).strip() or "zh",
        temperature=float(payload.get("temperature", 0.0) or 0.0),
        max_tokens=int(payload.get("max_tokens", 1024) or 1024),
        timeout_seconds=float(payload.get("timeout_seconds", 30.0) or 30.0),
        asr_timeout_seconds=float(payload.get("asr_timeout_seconds", 60.0) or 60.0),
        api_base=str(payload.get("api_base", "")).strip(),
        api_key=str(payload.get("api_key", "")).strip(),
    )


def llm_config_from_settings(payload: dict, base: LLMConfig | None = None) -> LLMConfig:
    base_config = base or load_llm_config()
    api_key = str(payload.get("OPENAI_API_KEY") or "").strip() or base_config.api_key or OPENAI_API_KEY
    api_base = str(payload.get("OPENAI_BASE_URL") or "").strip() or base_config.api_base or OPENAI_BASE_URL
    model = str(payload.get("OPENAI_CHAT_MODEL") or "").strip() or base_config.model or OPENAI_CHAT_MODEL
    temperature = str(payload.get("ROBOTCLAW_LLM_TEMPERATURE") or "").strip()
    return LLMConfig(
        profile_id="request",
        label="Request",
        provider="openai",
        model=model,
        asr_provider=base_config.asr_provider,
        asr_model=base_config.asr_model,
        asr_language=base_config.asr_language,
        temperature=float(temperature) if temperature else base_config.temperature,
        max_tokens=base_config.max_tokens,
        timeout_seconds=base_config.timeout_seconds,
        asr_timeout_seconds=base_config.asr_timeout_seconds,
        api_base=api_base,
        api_key=api_key,
    )


def _default_asr_provider() -> str:
    explicit = LLM_ASR_PROVIDER
    if explicit:
        return explicit
    if VOLCENGINE_ASR_WS_URL or VOLCENGINE_ASR_API_KEY or VOLCENGINE_ASR_ACCESS_KEY:
        return "volcengine"
    return "openai"
