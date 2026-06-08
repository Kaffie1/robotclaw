from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.gateway.app import GatewayApplication


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
            if parsed.path == "/api/chat/history":
                query = self.parse_query(parsed.query)
                session_id = str(query.get("session_id", "")).strip()
                self.send_json(app.chat_history(session_id))
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
                if parsed.path == "/api/chat/cancel":
                    self.send_json(
                        app.cancel_chat(
                            session_id=str(data.get("session_id", "")).strip(),
                            task_id=str(data.get("task_id", "")).strip(),
                        )
                    )
                    return
                if parsed.path == "/api/chat/resume":
                    self.send_json(
                        app.resume_chat(
                            session_id=str(data.get("session_id", "")).strip(),
                            task_id=str(data.get("task_id", "")).strip(),
                            token=str(data.get("resume_token", "")).strip(),
                            user_id=str(data.get("user_id", "u001")).strip() or "u001",
                        )
                    )
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

        def parse_query(self, query: str) -> dict[str, str]:
            parsed = parse_qs(query, keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items() if values}

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
