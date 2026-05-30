from .assistant import router as assistant_router
from .connection import router as connection_router
from .deploy import router as deploy_router
from .file_ops import router as file_ops_router
from .history import router as history_router
from .home import router as home_router
from .system import router as system_router

__all__ = [
    "assistant_router",
    "connection_router",
    "deploy_router",
    "file_ops_router",
    "history_router",
    "home_router",
    "system_router",
]
