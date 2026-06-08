from __future__ import annotations

from pathlib import Path

from backend.gateway.models import ChatRequest
from backend.runtime.models import DiagnosisSummary, RuntimeEnvelope
from backend.memory import MemoryManager
from backend.runtime import RuntimeService
from backend.session import SessionManager
from backend.ssh import SSHManager


class GatewayApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.memory_manager = MemoryManager()
        self.session_manager = SessionManager(memory_manager=self.memory_manager)
        self.runtime = RuntimeService(memory_manager=self.memory_manager)
        self.ssh_manager = SSHManager()

    def bootstrap(self) -> dict:
        payload = self.session_manager.bootstrap_payload()
        payload["connection"] = self.ssh_manager.ui_payload()
        return payload

    def create_session(self, user_id: str) -> dict:
        return self.session_manager.create_session_payload(user_id=user_id)

    def send_chat(self, session_id: str, user_id: str, content: str) -> dict:
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
        return self._run_chat(session_id=session_id, request=request)

    def resume_chat(self, session_id: str, task_id: str, token: str, user_id: str = "u001") -> dict:
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
        return self.session_manager.history_payload(session_id)

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
        self.session_manager.record_turn(session_id, "assistant", response.summary)
        self.session_manager.update_session_from_chat(session_id, request.content)
        self.session_manager.set_task_status(task.task_id, response.status, current_node="completed")
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
        self.ssh_manager.disconnect()
        return self.ssh_manager.ui_payload()
