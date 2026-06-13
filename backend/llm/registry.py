from __future__ import annotations

from threading import RLock

from backend.llm.client import LLMClient
from backend.llm.config import LLMConfig, llm_config_from_payload, load_llm_profiles


class LLMRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._profiles, self._active_profile_id = load_llm_profiles()
        self._active_client: LLMClient | None = None

    def get_active_client(self) -> LLMClient:
        with self._lock:
            if self._active_client is None:
                self._active_client = LLMClient(config=self._profiles[self._active_profile_id])
            return self._active_client

    def get_active_config(self) -> LLMConfig:
        with self._lock:
            return self._profiles[self._active_profile_id]

    def list_profiles(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "profile_id": config.profile_id,
                    "label": config.label,
                    "provider": config.provider,
                    "model": config.model,
                    "asr_provider": config.asr_provider,
                    "asr_model": config.asr_model,
                    "asr_language": config.asr_language,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "timeout_seconds": config.timeout_seconds,
                    "asr_timeout_seconds": config.asr_timeout_seconds,
                    "api_base": config.api_base,
                    "has_api_key": bool(config.api_key),
                    "active": config.profile_id == self._active_profile_id,
                }
                for config in self._profiles.values()
            ]

    def activate(self, profile_id: str) -> LLMConfig:
        with self._lock:
            if profile_id not in self._profiles:
                raise ValueError(f"未知模型配置: {profile_id}")
            self._active_profile_id = profile_id
            self._active_client = None
            return self._profiles[profile_id]

    def upsert_profile(self, payload: dict, activate: bool = False) -> LLMConfig:
        config = llm_config_from_payload(payload)
        with self._lock:
            self._profiles[config.profile_id] = config
            if activate:
                self._active_profile_id = config.profile_id
            if activate or config.profile_id == self._active_profile_id:
                self._active_client = None
            return config

    def status_payload(self) -> dict:
        active = self.get_active_config()
        return {
            "active_profile_id": active.profile_id,
            "active_model": active.model,
            "active_asr_provider": active.asr_provider,
            "active_asr_model": active.asr_model,
            "active_provider": active.provider,
            "profiles": self.list_profiles(),
        }
