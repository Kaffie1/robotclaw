import threading
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.config import SESSION_CLEANUP_INTERVAL_SECONDS, SESSION_COOKIE, SESSION_IDLE_TIMEOUT_SECONDS, STATIC_DIR
from ..core.models import ApiError
from ..infra.container import session_store
from .routes import (
    assistant_router,
    connection_router,
    deploy_router,
    file_ops_router,
    history_router,
    home_router,
    system_router,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_event = threading.Event()

    def cleanup_loop() -> None:
        while not stop_event.wait(SESSION_CLEANUP_INTERVAL_SECONDS):
            session_store.cleanup_expired(SESSION_IDLE_TIMEOUT_SECONDS)

    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        cleanup_thread.join(timeout=1)
        session_store.close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Upgrade Console", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def attach_session(request: Request, call_next):
        sid = request.cookies.get(SESSION_COOKIE)
        sid, session, is_new = session_store.get_or_create(sid)
        session_store.touch(sid)
        request.state.session_id = sid
        request.state.session = session
        response = await call_next(request)
        if is_new:
            response.set_cookie(SESSION_COOKIE, sid, path="/", httponly=True, samesite="lax")
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.message, **exc.payload})
        return PlainTextResponse(exc.message, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        message = errors[0].get("msg", "请求参数无效") if errors else "请求参数无效"
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=400, content={"ok": False, "error": message})
        return PlainTextResponse(message, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": str(exc.detail)})
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        traceback.print_exc()
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        return PlainTextResponse(str(exc), status_code=500)

    app.include_router(home_router)
    app.include_router(assistant_router)
    app.include_router(connection_router)
    app.include_router(history_router)
    app.include_router(file_ops_router)
    app.include_router(system_router)
    app.include_router(deploy_router)
    return app
