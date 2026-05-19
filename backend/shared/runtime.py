from datetime import datetime

from fastapi.templating import Jinja2Templates

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


from ..core.config import CONNECTION_CACHE_PATH, DB_PATH, DEFAULT_DEPLOY_CONFIG, DEPLOY_CONFIG_PATH, TEMPLATE_DIR
from ..infra.stores import ConnectionCacheStore, DeployConfigStore, HistoryStore, SessionStore, TaskManager, UploadProgressManager
from .files import migrate_legacy_runtime_files


migrate_legacy_runtime_files()
history_store = HistoryStore(DB_PATH)
task_manager = TaskManager(history_store)
session_store = SessionStore()
upload_progress_manager = UploadProgressManager()
upload_progress_manager.set_update_callback(task_manager.sync_progress_from_upload)
connection_cache_store = ConnectionCacheStore(CONNECTION_CACHE_PATH)
deploy_config_store = DeployConfigStore(DEPLOY_CONFIG_PATH, DEFAULT_DEPLOY_CONFIG)
deploy_config_store.ensure_exists()
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
