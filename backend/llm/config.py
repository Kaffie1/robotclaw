from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "mock"
    model: str = "robotclaw-mock"
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    api_base: str = ""
    api_key: str = ""


def load_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=os.getenv("ROBOTCLAW_LLM_PROVIDER", "mock").strip() or "mock",
        model=os.getenv("ROBOTCLAW_LLM_MODEL", "robotclaw-mock").strip() or "robotclaw-mock",
        temperature=float(os.getenv("ROBOTCLAW_LLM_TEMPERATURE", "0") or "0"),
        max_tokens=int(os.getenv("ROBOTCLAW_LLM_MAX_TOKENS", "1024") or "1024"),
        timeout_seconds=float(os.getenv("ROBOTCLAW_LLM_TIMEOUT", "30") or "30"),
        api_base=os.getenv("ROBOTCLAW_LLM_API_BASE", "").strip(),
        api_key=os.getenv("ROBOTCLAW_LLM_API_KEY", "").strip(),
    )
