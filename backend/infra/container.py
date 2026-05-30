from fastapi.templating import Jinja2Templates

from ..core.config import CONNECTION_CACHE_PATH, DB_PATH, DEFAULT_DEPLOY_PAGE_CONFIG, DEPLOY_CONFIG_PATH, TEMPLATE_DIR
from ..data import ConnectionCacheStore, DeployConfigStore, HistoryStore, SessionStore
from ..runtime.tasks import TaskManager, UploadProgressManager
from ..core.files import migrate_legacy_runtime_files


migrate_legacy_runtime_files()
history_store = HistoryStore(DB_PATH)
task_manager = TaskManager(history_store)
session_store = SessionStore()
upload_progress_manager = UploadProgressManager()
upload_progress_manager.set_update_callback(task_manager.sync_progress_from_upload)
connection_cache_store = ConnectionCacheStore(CONNECTION_CACHE_PATH)
deploy_config_store = DeployConfigStore(DEPLOY_CONFIG_PATH, DEFAULT_DEPLOY_PAGE_CONFIG)
deploy_config_store.ensure_exists()
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


__all__ = [
    "connection_cache_store",
    "deploy_config_store",
    "history_store",
    "session_store",
    "task_manager",
    "templates",
    "upload_progress_manager",
]
