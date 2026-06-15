from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.gateway.app import GatewayApplication
from backend.shared import get_logger


logger = get_logger("gateway.http")


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
            if parsed.path == "/api/llm/status":
                self.send_json(app.llm_status())
                return
            if parsed.path == "/api/speech/status":
                self.send_json(app.speech_status())
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
                    self.send_json(
                        app.create_session(
                            user_id,
                            interaction_mode=str(data.get("interaction_mode", "")).strip(),
                        ),
                        status=HTTPStatus.CREATED,
                    )
                    return
                if parsed.path == "/api/session/mode":
                    self.send_json(
                        app.set_session_mode(
                            session_id=str(data.get("session_id", "")).strip(),
                            interaction_mode=str(data.get("interaction_mode", "")).strip(),
                        )
                    )
                    return
                if parsed.path == "/api/chat/send":
                    payload = app.send_chat(
                        session_id=str(data.get("session_id", "")).strip(),
                        user_id=str(data.get("user_id", "u001")).strip() or "u001",
                        content=str(data.get("content", "")),
                    )
                    self.send_json(payload)
                    return
                if parsed.path == "/api/chat/voice/send":
                    payload = app.send_voice_chat(
                        session_id=str(data.get("session_id", "")).strip(),
                        user_id=str(data.get("user_id", "u001")).strip() or "u001",
                        audio_base64=str(data.get("audio_base64", "")),
                        mime_type=str(data.get("mime_type", "")).strip(),
                        filename=str(data.get("filename", "")).strip(),
                        language=str(data.get("language", "")).strip(),
                    )
                    self.send_json(payload)
                    return
                if parsed.path == "/api/speech/transcribe":
                    transcription = app.transcribe_audio(
                        audio_base64=str(data.get("audio_base64", "")),
                        mime_type=str(data.get("mime_type", "")).strip(),
                        filename=str(data.get("filename", "")).strip(),
                        language=str(data.get("language", "")).strip(),
                    )
                    self.send_json(
                        {
                            "text": transcription.text,
                            "model": transcription.model,
                            "raw": transcription.raw,
                        }
                    )
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
                            port=data.get("port", 22),
                            username=str(data.get("username", "")),
                            password=str(data.get("password", "")),
                            private_key_path=str(data.get("private_key_path", "")),
                            ros_version=str(data.get("ros_version", "")),
                            workspace=str(data.get("workspace", "")),
                            setup_script=str(data.get("setup_script", "")),
                        )
                    )
                    return
                if parsed.path == "/api/robot/disconnect":
                    self.send_json(app.disconnect_robot())
                    return
                if parsed.path == "/api/llm/activate":
                    self.send_json(
                        app.activate_llm_profile(
                            profile_id=str(data.get("profile_id", "")).strip(),
                        )
                    )
                    return
                if parsed.path == "/api/llm/profiles":
                    self.send_json(
                        app.upsert_llm_profile(
                            payload=data,
                            activate=bool(data.get("activate", False)),
                        ),
                        status=HTTPStatus.CREATED,
                    )
                    return
            except ValueError as exc:
                logger.warning("Bad request on %s: %s", parsed.path, exc)
                self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except KeyError as exc:
                logger.warning("Missing resource on %s: %s", parsed.path, exc)
                self.send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except Exception:
                logger.exception("Unhandled error while processing %s", parsed.path)
                self.send_json({"error": "Internal server error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
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


def run_dev_server(root: Path, host: str = "0.0.0.0", port: int = 8005) -> None:
    app = GatewayApplication(root=root)
    handler = build_handler(app)
    server = ThreadingHTTPServer((host, port), handler)
    logger.info("RobotClaw server running at http://%s:%s/frontend/", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("RobotClaw server interrupted by keyboard signal")
    finally:
        logger.info("RobotClaw server shutting down")
        server.server_close()
