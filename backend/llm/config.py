from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    profile_id: str = "default"
    label: str = "Default"
    provider: str = "openai"
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    api_base: str = ""
    api_key: str = ""


def load_llm_config() -> LLMConfig:
    return LLMConfig(
        profile_id="default",
        label="Default",
        provider=os.getenv("ROBOTCLAW_LLM_PROVIDER", "openai").strip() or "openai",
        model=os.getenv("ROBOTCLAW_LLM_MODEL", "").strip(),
        temperature=float(os.getenv("ROBOTCLAW_LLM_TEMPERATURE", "0") or "0"),
        max_tokens=int(os.getenv("ROBOTCLAW_LLM_MAX_TOKENS", "1024") or "1024"),
        timeout_seconds=float(os.getenv("ROBOTCLAW_LLM_TIMEOUT", "30") or "30"),
        api_base=os.getenv("ROBOTCLAW_LLM_API_BASE", "").strip(),
        api_key=os.getenv("ROBOTCLAW_LLM_API_KEY", "").strip(),
    )


def load_llm_profiles() -> tuple[dict[str, LLMConfig], str]:
    raw_profiles = os.getenv("ROBOTCLAW_LLM_PROFILES", "").strip()
    active_profile_id = os.getenv("ROBOTCLAW_LLM_ACTIVE_PROFILE", "").strip() or "default"
    profiles: dict[str, LLMConfig] = {}

    if raw_profiles:
        payload = json.loads(raw_profiles)
        if not isinstance(payload, list):
            raise ValueError("ROBOTCLAW_LLM_PROFILES must be a JSON array")
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
                temperature=float(item.get("temperature", 0.0) or 0.0),
                max_tokens=int(item.get("max_tokens", 1024) or 1024),
                timeout_seconds=float(item.get("timeout_seconds", 30.0) or 30.0),
                api_base=str(item.get("api_base", "")).strip(),
                api_key=str(item.get("api_key", "")).strip(),
            )

    if not profiles:
        default_config = load_llm_config()
        profiles[default_config.profile_id] = default_config

        openai_model = os.getenv("OPENAI_CHAT_MODEL", "").strip()
        openai_base = os.getenv("OPENAI_BASE_URL", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_model:
            profiles["openai"] = LLMConfig(
                profile_id="openai",
                label="OpenAI-Compatible",
                provider="openai",
                model=openai_model,
                temperature=default_config.temperature,
                max_tokens=default_config.max_tokens,
                timeout_seconds=default_config.timeout_seconds,
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
        temperature=float(payload.get("temperature", 0.0) or 0.0),
        max_tokens=int(payload.get("max_tokens", 1024) or 1024),
        timeout_seconds=float(payload.get("timeout_seconds", 30.0) or 30.0),
        api_base=str(payload.get("api_base", "")).strip(),
        api_key=str(payload.get("api_key", "")).strip(),
    )
