from __future__ import annotations

from pathlib import Path

from backend.gateway.models import ChatRequest
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope
from backend.memory import MemoryManager
from backend.runtime import RuntimeService
from backend.session import SessionManager
from backend.shared import get_logger, load_env_file
from backend.ssh import SSHManager


logger = get_logger("gateway.app")


class GatewayApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        load_env_file(root / ".env")
        self.memory_manager = MemoryManager()
        self.session_manager = SessionManager(memory_manager=self.memory_manager)
        self.runtime = RuntimeService(memory_manager=self.memory_manager)
        self.ssh_manager = SSHManager()

    def bootstrap(self) -> dict:
        logger.info("Bootstrap requested")
        payload = self.session_manager.bootstrap_payload()
        payload["connection"] = self.ssh_manager.ui_payload()
        payload["llm"] = self.runtime.llm_status()
        return payload

    def create_session(self, user_id: str) -> dict:
        logger.info("Creating session for user_id=%s", user_id)
        return self.session_manager.create_session_payload(user_id=user_id)

    def send_chat(self, session_id: str, user_id: str, content: str) -> dict:
        logger.info("Received chat request session_id=%s user_id=%s", session_id, user_id)
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
        return self._run_chat(session_id=session_id, request=request)

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
        _state, _diagnosis, response = self.runtime.run(
            envelope=envelope,
            request=request,
            connected=self.ssh_manager.current_state().connected,
        )
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

    def connect_robot(self, name: str, host: str) -> dict:
        logger.info("Connecting robot name=%s host=%s", name, host)
        config, state = self.ssh_manager.connect(
            robot_ref=name.strip() or "robot-001",
            host=host.strip() or "192.168.1.100",
        )
        sessions = self.session_manager.list_sessions()
        if sessions:
            session = self.session_manager.get_session_state(sessions[0]["id"])
            session.current_robot_ref = config.robot_ref
        return {
            "connected": state.connected,
            "name": state.robot_ref,
            "host": state.host,
        }

    def disconnect_robot(self) -> dict:
        logger.info("Disconnecting robot")
        self.ssh_manager.disconnect()
        return self.ssh_manager.ui_payload()
