from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.models import DiagnosisSummary, RuntimeEnvelope
from backend.runtime import RuntimeService
from backend.session_manager import SessionManager
from backend.ssh_manager import SSHManager


class GatewayApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.session_manager = SessionManager()
        self.runtime = RuntimeService()
        self.ssh_manager = SSHManager()

    def bootstrap(self) -> dict:
        payload = self.session_manager.bootstrap_payload()
        payload["connection"] = self.ssh_manager.ui_payload()
        return payload

    def create_session(self, user_id: str) -> dict:
        return self.session_manager.create_session_payload(user_id=user_id)

    def send_chat(self, session_id: str, user_id: str, content: str) -> dict:
        request = self.runtime.build_request(session_id=session_id, user_id=user_id, content=content)
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
            "session": self.session_manager.list_sessions()[0],
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
        config, state = self.ssh_manager.connect(robot_ref=name.strip() or "robot-001", host=host.strip() or "192.168.1.100")
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


def build_handler(app: GatewayApplication):
    class AppHandler(BaseHTTPRequestHandler):
        server_version = "RobotClaw/0.2"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/bootstrap":
                self.send_json(app.bootstrap())
                return
            if parsed.path == "/api/robot/status":
                self.send_json(app.ssh_manager.ui_payload())
                return
            self.serve_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            data = self.read_json()
            try:
                if parsed.path == "/api/sessions":
                    user_id = str(data.get("user_id", "u001")).strip() or "u001"
                    self.send_json(app.create_session(user_id), status=HTTPStatus.CREATED)
                    return
                if parsed.path == "/api/chat/send":
                    payload = app.send_chat(
                        session_id=str(data.get("session_id", "")).strip(),
                        user_id=str(data.get("user_id", "u001")).strip() or "u001",
                        content=str(data.get("content", "")),
                    )
                    self.send_json(payload)
                    return
                if parsed.path == "/api/robot/connect":
                    self.send_json(
                        app.connect_robot(
                            name=str(data.get("name", "")),
                            host=str(data.get("host", "")),
                        )
                    )
                    return
                if parsed.path == "/api/robot/disconnect":
                    self.send_json(app.disconnect_robot())
                    return
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except KeyError as exc:
                self.send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return

            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            body = self.rfile.read(length)
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))

        def serve_static(self, path: str) -> None:
            normalized = path or "/"
            if normalized == "/":
                normalized = "/frontend/"
            if normalized == "/frontend":
                normalized = "/frontend/"
            if normalized.endswith("/"):
                normalized = normalized + "index.html"

            target = (app.root / normalized.lstrip("/")).resolve()
            if app.root not in target.parents and target != app.root:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            mime_type, _ = mimetypes.guess_type(str(target))
            content_type = mime_type or "application/octet-stream"
            content = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    return AppHandler


def run_dev_server(root: Path, host: str = "127.0.0.1", port: int = 8001) -> None:
    app = GatewayApplication(root=root)
    handler = build_handler(app)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"RobotClaw server running at http://{host}:{port}/frontend/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
