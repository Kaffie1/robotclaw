from __future__ import annotations

import base64
import binascii
from pathlib import Path

from backend.llm import AudioTranscriptionResponse, LLMClient
from backend.llm.config import llm_config_from_settings
from backend.llm.volc_asr import load_volc_asr_config
from backend.gateway.models import ChatRequest
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope
from backend.memory import MemoryManager
from backend.runtime import RuntimeService
from backend.session import SessionManager
from backend.shared import get_logger, load_env_file, strip_image_attachment_summary
from backend.shared.config import SPEECH_AUTO_SEND


logger = get_logger("gateway.app")

DEFAULT_OPENAI_BASE_URL = ""
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_LLM_TEMPERATURE = "0"
DEFAULT_TOP_K = "4"


class GatewayApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        load_env_file(root / ".env")
        self.memory_manager = MemoryManager()
        self.session_manager = SessionManager(memory_manager=self.memory_manager)
        self.runtime = RuntimeService(memory_manager=self.memory_manager)

    def bootstrap(self) -> dict:
        logger.info("Bootstrap requested")
        payload = self.session_manager.bootstrap_payload()
        payload["llm"] = self.runtime.llm_status()
        payload["speech"] = self.speech_status()
        return payload

    def create_session(self, user_id: str, interaction_mode: str = "") -> dict:
        del interaction_mode
        logger.info("Creating QA session for user_id=%s", user_id)
        return self.session_manager.create_session_payload(user_id=user_id, interaction_mode="qa")

    def send_chat(
        self,
        session_id: str,
        user_id: str,
        content: str,
        images: list[dict] | None = None,
        llm_settings: dict | None = None,
    ) -> dict:
        logger.info("Received chat request session_id=%s user_id=%s", session_id, user_id)
        request = self.runtime.build_request(
            session_id=session_id,
            user_id=user_id,
            content=content,
            images=self._normalize_image_attachments(images or []),
        )
        request.llm_settings = self._normalize_settings_payload(llm_settings or {})
        return self._run_chat(session_id=session_id, request=request)

    def send_voice_chat(
        self,
        session_id: str,
        user_id: str,
        *,
        audio_base64: str = "",
        mime_type: str = "",
        filename: str = "",
        language: str = "",
        llm_settings: dict | None = None,
    ) -> dict:
        transcription = self.transcribe_audio(
            audio_base64=audio_base64,
            mime_type=mime_type,
            filename=filename,
            language=language,
            llm_settings=llm_settings,
        )
        content = transcription.text.strip()
        logger.info("Received voice chat request session_id=%s user_id=%s", session_id, user_id)
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
        request.llm_settings = self._normalize_settings_payload(llm_settings or {})
        payload = self._run_chat(session_id=session_id, request=request)
        payload["transcript"] = {
            "text": transcription.text,
            "model": transcription.model,
        }
        return payload

    def resume_chat(self, session_id: str, task_id: str, token: str, user_id: str = "u001") -> dict:
        logger.info("Resuming chat session_id=%s task_id=%s user_id=%s", session_id, task_id, user_id)
        memory = self.session_manager.get_memory(session_id)
        user_messages = [turn.content for turn in memory.chat_history if turn.role == "user"]
        if not user_messages:
            raise ValueError("当前会话没有可恢复的用户输入")
        request = self.runtime.resume_request(
            session_id=session_id,
            task_id=task_id,
            content=user_messages[-1],
            token=token,
            user_id=user_id,
        )
        return self._run_chat(session_id=session_id, request=request)

    def cancel_chat(self, session_id: str, task_id: str) -> dict:
        logger.info("Cancelling chat session_id=%s task_id=%s", session_id, task_id)
        token = self.runtime.interrupt_task(session_id=session_id, task_id=task_id)
        self.session_manager.set_task_status(task_id, "interrupted", current_node="interrupted")
        return {
            "session_id": session_id,
            "task_id": task_id,
            "status": "interrupted",
            "resume_token": token,
            "runtime": self.runtime.get_runtime_payload(task_id),
        }

    def chat_history(self, session_id: str) -> dict:
        logger.info("Fetching chat history session_id=%s", session_id)
        return self.session_manager.history_payload(session_id)

    def llm_status(self) -> dict:
        return self.runtime.llm_status()

    def settings_payload(self) -> dict:
        active_config = self.runtime.llm_registry.get_active_config()
        return {
            "settings": {
                "ROBOTCLAW_LLM_TEMPERATURE": "",
                "TOP_K": "",
                "OPENAI_API_KEY": "",
                "OPENAI_BASE_URL": "",
                "OPENAI_CHAT_MODEL": "",
            },
            "defaults": {
                "ROBOTCLAW_LLM_TEMPERATURE": str(active_config.temperature),
                "TOP_K": DEFAULT_TOP_K,
                "OPENAI_BASE_URL": active_config.api_base or DEFAULT_OPENAI_BASE_URL,
                "OPENAI_CHAT_MODEL": active_config.model or DEFAULT_OPENAI_CHAT_MODEL,
            },
            "required": ["OPENAI_API_KEY"],
        }

    def save_settings(self, payload: dict) -> dict:
        settings = self._normalize_settings_payload(payload)
        if not settings["OPENAI_API_KEY"]:
            raise ValueError("OPENAI_API_KEY 不能为空")
        return {
            **self.settings_payload(),
            "settings": settings,
        }

    def speech_status(self) -> dict:
        config = self.runtime.llm_registry.get_active_config()
        display_model = config.asr_model
        display_language = config.asr_language
        display_endpoint = config.api_base
        has_api_key = bool(config.api_key)
        asr_enabled = False
        if config.asr_provider == "volcengine":
            volc_config = load_volc_asr_config()
            display_model = volc_config.asr_model
            display_language = volc_config.language
            display_endpoint = volc_config.ws_url
            has_api_key = bool(volc_config.api_key or volc_config.access_key)
            asr_enabled = bool(
                volc_config.ws_url
                and volc_config.resource_id
                and (volc_config.api_key or (volc_config.app_key and volc_config.access_key))
            )
        else:
            asr_enabled = bool(config.asr_model and config.api_base and config.api_key)
        return {
            "asr_enabled": asr_enabled,
            "auto_send": SPEECH_AUTO_SEND,
            "provider": config.asr_provider,
            "model": display_model,
            "language": display_language,
            "has_api_key": has_api_key,
            "api_base": display_endpoint,
        }

    def transcribe_audio(
        self,
        *,
        audio_base64: str,
        mime_type: str = "",
        filename: str = "",
        language: str = "",
        llm_settings: dict | None = None,
    ) -> AudioTranscriptionResponse:
        audio_bytes = self._decode_audio_base64(audio_base64)
        effective_mime_type = mime_type.strip() or "audio/webm"
        effective_filename = filename.strip() or self._default_audio_filename(effective_mime_type)
        llm_client = self._build_request_llm_client(self._normalize_settings_payload(llm_settings or {}))
        try:
            return llm_client.transcribe_audio(
                audio_bytes=audio_bytes,
                filename=effective_filename,
                mime_type=effective_mime_type,
                language=language.strip() or None,
            )
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("ASR failed mime_type=%s filename=%s", effective_mime_type, effective_filename)
            raise ValueError("ASR 转写失败") from exc

    def activate_llm_profile(self, profile_id: str) -> dict:
        logger.info("Activating llm profile profile_id=%s", profile_id)
        return self.runtime.activate_llm_profile(profile_id=profile_id)

    def upsert_llm_profile(self, payload: dict, activate: bool = False) -> dict:
        logger.info("Upserting llm profile profile_id=%s activate=%s", payload.get("profile_id", ""), activate)
        return self.runtime.upsert_llm_profile(payload=payload, activate=activate)

    def _run_chat(self, session_id: str, request: ChatRequest) -> dict:
        display_content = self._display_request_content(request)
        task = self.session_manager.ensure_active_task(session_id, title=display_content)
        session = self.session_manager.get_session_state(session_id)
        self.session_manager.set_task_status(task.task_id, "running", current_node="runtime")
        self.session_manager.record_turn(
            session_id,
            "user",
            display_content,
            metadata=self._display_request_metadata(request),
        )

        envelope = RuntimeEnvelope(
            session=session,
            task=task,
            diagnosis=DiagnosisSummary(),
        )
        try:
            _state, _diagnosis, response = self.runtime.run(
                envelope=envelope,
                request=request,
                connected=False,
            )
        except Exception as exc:
            raise ValueError(self._user_facing_runtime_error(exc, has_images=bool(request.images))) from exc
        logger.info(
            "Chat finished session_id=%s task_id=%s status=%s current_step=%s",
            session_id,
            task.task_id,
            response.status,
            _state.current_step,
        )
        self.session_manager.record_turn(
            session_id,
            "assistant",
            response.summary,
            metadata={"metrics": response.data.get("metrics", {})},
        )
        self.session_manager.update_session_from_chat(session_id, display_content)
        self.session_manager.set_task_status(task.task_id, response.status, current_node=_state.current_step)
        return {
            "session": self.session_manager.session_payload(session_id),
            "active_session_id": session_id,
            "response": {
                "session_id": response.session_id,
                "task_id": response.task_id,
                "status": response.status,
                "summary": response.summary,
                "continuation_token": response.continuation_token,
                "playbook_id": response.playbook_id,
                "data": response.data,
            },
        }

    def _normalize_settings_payload(self, payload: dict) -> dict[str, str]:
        temperature = str(payload.get("ROBOTCLAW_LLM_TEMPERATURE", "")).strip()
        top_k = str(payload.get("TOP_K", "")).strip()
        api_key = str(payload.get("OPENAI_API_KEY", "")).strip()
        api_base = str(payload.get("OPENAI_BASE_URL", "")).strip()
        chat_model = str(payload.get("OPENAI_CHAT_MODEL", "")).strip()

        if temperature:
            float(temperature)
        if top_k:
            parsed_top_k = int(top_k)
            if parsed_top_k <= 0:
                raise ValueError("TOP_K 必须大于 0")
        return {
            "ROBOTCLAW_LLM_TEMPERATURE": temperature,
            "TOP_K": top_k,
            "OPENAI_API_KEY": api_key,
            "OPENAI_BASE_URL": api_base,
            "OPENAI_CHAT_MODEL": chat_model,
        }

    def _build_request_llm_client(self, llm_settings: dict) -> LLMClient:
        base_config = self.runtime.llm_registry.get_active_config()
        return LLMClient(config=llm_config_from_settings(llm_settings, base=base_config))

    def _display_request_content(self, request: ChatRequest) -> str:
        return strip_image_attachment_summary(request.content)

    def _display_request_metadata(self, request: ChatRequest) -> dict:
        if not request.images:
            return {}
        return {"images": list(request.images)}

    def _decode_audio_base64(self, value: str) -> bytes:
        encoded = str(value or "").strip()
        if not encoded:
            raise ValueError("audio_base64 不能为空")
        if "," in encoded and encoded.lower().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        try:
            audio_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("audio_base64 非法") from exc
        if not audio_bytes:
            raise ValueError("音频数据为空")
        return audio_bytes

    def _normalize_image_attachments(self, images: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for image in images[:4]:
            if not isinstance(image, dict):
                continue
            source = image.get("source") if isinstance(image.get("source"), dict) else {}
            raw_data = str(image.get("data") or source.get("data") or "").strip()
            if "," in raw_data and raw_data.lower().startswith("data:"):
                raw_data = raw_data.split(",", 1)[1]
            if not raw_data:
                continue
            try:
                image_bytes = base64.b64decode(raw_data, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("图片 base64 非法") from exc
            if len(image_bytes) > 5 * 1024 * 1024:
                raise ValueError("单张图片不能超过 5MB")
            media_type = str(image.get("media_type") or source.get("media_type") or "image/png").strip().lower()
            if media_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
                raise ValueError(f"不支持的图片类型：{media_type}")
            normalized.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": raw_data,
                    },
                    "name": str(image.get("name") or "").strip(),
                }
            )
        return normalized

    def _default_audio_filename(self, mime_type: str) -> str:
        normalized = mime_type.strip().lower()
        if normalized == "audio/wav":
            return "audio.wav"
        if normalized == "audio/mp3" or normalized == "audio/mpeg":
            return "audio.mp3"
        if normalized == "audio/mp4":
            return "audio.m4a"
        if normalized == "audio/ogg":
            return "audio.ogg"
        return "audio.webm"

    def _user_facing_runtime_error(self, exc: Exception, *, has_images: bool = False) -> str:
        message = str(exc).strip()
        normalized = message.lower()
        if "account_expired" in normalized or "account expired" in normalized:
            return "当前聊天模型账号已过期，请更换可用的 OPENAI_API_KEY 或充值后重试"
        if "permissiondenied" in normalized or "permission denied" in normalized or "403" in normalized:
            return "当前聊天模型认证失败或无权限，请检查 OPENAI_API_KEY、OPENAI_BASE_URL 和模型配置"
        if "unsupported capability" in normalized:
            if has_images:
                return "当前聊天模型或接口不支持图片理解能力，请切换到支持图片的模型，或删除图片后重试"
            return "当前聊天模型或接口拒绝了本次请求能力，请检查模型名称、OPENAI_BASE_URL 是否匹配，或更换兼容模型后重试"
        if "rate_limit" in normalized or "429" in normalized or "用量上限" in message:
            return "当前聊天模型额度已用尽，请更换可用模型或充值后重试"
        if message:
            return f"聊天调用失败：{message}"
        return "聊天调用失败，请稍后重试"
