from __future__ import annotations

import base64
import binascii
from pathlib import Path

from backend.llm import AudioTranscriptionResponse
from backend.llm.volc_asr import load_volc_asr_config
from backend.gateway.models import ChatRequest
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope
from backend.memory import MemoryManager
from backend.runtime import RuntimeService
from backend.session import SessionManager
from backend.shared import get_logger, load_env_file
from backend.shared.config import SPEECH_AUTO_SEND
from backend.ssh import RobotConnectionConfig, SSHManager
from backend.tools import ToolExecutor


logger = get_logger("gateway.app")


class GatewayApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        load_env_file(root / ".env")
        self.memory_manager = MemoryManager()
        self.session_manager = SessionManager(memory_manager=self.memory_manager)
        self.ssh_manager = SSHManager()
        self.runtime = RuntimeService(
            memory_manager=self.memory_manager,
            tool_executor=ToolExecutor(ssh_manager=self.ssh_manager),
        )

    def bootstrap(self) -> dict:
        logger.info("Bootstrap requested")
        payload = self.session_manager.bootstrap_payload()
        payload["connection"] = self.ssh_manager.ui_payload()
        payload["llm"] = self.runtime.llm_status()
        payload["speech"] = self.speech_status()
        return payload

    def create_session(self, user_id: str) -> dict:
        logger.info("Creating session for user_id=%s", user_id)
        return self.session_manager.create_session_payload(user_id=user_id)

    def send_chat(self, session_id: str, user_id: str, content: str) -> dict:
        logger.info("Received chat request session_id=%s user_id=%s", session_id, user_id)
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
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
    ) -> dict:
        transcription = self.transcribe_audio(
            audio_base64=audio_base64,
            mime_type=mime_type,
            filename=filename,
            language=language,
        )
        content = transcription.text.strip()
        logger.info("Received voice chat request session_id=%s user_id=%s", session_id, user_id)
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
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
        session = self.session_manager.get_session_state(session_id)
        token = self.runtime.interrupt_task(session_id=session_id, task_id=task_id)
        self.session_manager.set_task_status(task_id, "interrupted", current_node="interrupted")
        return {
            "session_id": session_id,
            "task_id": task_id,
            "status": "interrupted",
            "resume_token": token,
            "runtime": self.runtime.get_runtime_payload(task_id),
            "active_robot_ref": session.current_robot_ref,
        }

    def chat_history(self, session_id: str) -> dict:
        logger.info("Fetching chat history session_id=%s", session_id)
        return self.session_manager.history_payload(session_id)

    def llm_status(self) -> dict:
        return self.runtime.llm_status()

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
    ) -> AudioTranscriptionResponse:
        audio_bytes = self._decode_audio_base64(audio_base64)
        effective_mime_type = mime_type.strip() or "audio/webm"
        effective_filename = filename.strip() or self._default_audio_filename(effective_mime_type)
        llm_client = self.runtime.llm_registry.get_active_client()
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
        task = self.session_manager.ensure_active_task(session_id, title=request.content)
        session = self.session_manager.get_session_state(session_id)
        session.current_robot_ref = self.ssh_manager.current_config().robot_ref
        self.session_manager.set_task_status(task.task_id, "running", current_node="runtime")
        self.session_manager.record_turn(session_id, "user", request.content)

        envelope = RuntimeEnvelope(
            session=session,
            task=task,
            diagnosis=DiagnosisSummary(),
            robot_config=self.ssh_manager.current_config(),
        )
        try:
            _state, _diagnosis, response = self.runtime.run(
                envelope=envelope,
                request=request,
                connected=self.ssh_manager.current_state().connected,
            )
        except Exception as exc:
            raise ValueError(self._user_facing_runtime_error(exc)) from exc
        logger.info(
            "Chat finished session_id=%s task_id=%s status=%s current_step=%s",
            session_id,
            task.task_id,
            response.status,
            _state.current_step,
        )
        self.session_manager.record_turn(session_id, "assistant", response.summary)
        self.session_manager.update_session_from_chat(session_id, request.content)
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

    def connect_robot(
        self,
        name: str,
        host: str,
        *,
        port: int | str = 22,
        username: str = "",
        password: str = "",
        private_key_path: str = "",
        ros_version: str = "",
        workspace: str = "",
        setup_script: str = "",
    ) -> dict:
        logger.info("Connecting robot name=%s host=%s port=%s username=%s", name, host, port, username)
        config, state = self.ssh_manager.connect(
            config=RobotConnectionConfig(
                robot_ref=name.strip() or "naviai",
                host=host.strip() or "172.16.9.136",
                port=self._normalize_port(port),
                username=username.strip() or "naviai",
                password=password or "naviai@2024",
                private_key_path=private_key_path.strip(),
                ros_version=ros_version.strip(),
                workspace=workspace.strip(),
                setup_script=setup_script.strip(),
            )
        )
        if not state.connected:
            error_message = str(state.last_error or "SSH 连接失败").strip() or "SSH 连接失败"
            raise ValueError(f"连接机器人失败：{error_message}")

        sessions = self.session_manager.list_sessions()
        if sessions:
            session = self.session_manager.get_session_state(sessions[0]["id"])
            session.current_robot_ref = config.robot_ref
        return self.ssh_manager.ui_payload()

    def disconnect_robot(self) -> dict:
        logger.info("Disconnecting robot")
        self.ssh_manager.disconnect()
        return self.ssh_manager.ui_payload()

    def _normalize_port(self, value: int | str) -> int:
        try:
            port = int(str(value or 22).strip() or "22")
        except (TypeError, ValueError):
            port = 22
        return port if port > 0 else 22

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

    def _user_facing_runtime_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        normalized = message.lower()
        if "rate_limit" in normalized or "429" in normalized or "用量上限" in message:
            return "当前聊天模型额度已用尽，请更换可用模型或充值后重试"
        if message:
            return f"聊天调用失败：{message}"
        return "聊天调用失败，请稍后重试"
