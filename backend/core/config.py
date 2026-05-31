import os
from pathlib import Path


def load_env_file(env_path: str | Path) -> None:
    path = Path(env_path)
    if not path.exists() or not path.is_file():
        return
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        normalized_value = value.strip()
        if len(normalized_value) >= 2 and normalized_value[0] == normalized_value[-1] and normalized_value[0] in {"'", '"'}:
            normalized_value = normalized_value[1:-1]
        os.environ.setdefault(normalized_key, normalized_value)


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_env_file(BASE_DIR / ".env")


def normalize_app_edition(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"robot", "robotics", "local"}:
        return "robot"
    return "server"

# ========== OpenAI API 配置 ==========
OPENAI_API_KEY = str(os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_BASE_URL = str(os.getenv("OPENAI_BASE_URL") or "").strip()
OPENAI_CHAT_MODEL = str(os.getenv("OPENAI_CHAT_MODEL") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
OPENAI_CHAT_TEMPERATURE = float(str(os.getenv("OPENAI_CHAT_TEMPERATURE") or "0.2").strip() or "0.2")
OPENAI_ENABLE_REASONING_SPLIT = str(os.getenv("OPENAI_ENABLE_REASONING_SPLIT") or "").strip().lower() in {"1", "true", "yes", "on"}
OPENAI_THINK = str(os.getenv("OPENAI_THINK") or "").strip()

# ========== Embedding 配置 ==========
EMBEDDING_PROVIDER = str(os.getenv("EMBEDDING_PROVIDER") or "huggingface").strip() or "huggingface"  # Embedding提供者: "huggingface" 或 "openai"
EMBEDDING_API_KEY = str(os.getenv("EMBEDDING_API_KEY") or "").strip()  # Embedding API密钥
EMBEDDING_BASE_URL = str(os.getenv("EMBEDDING_BASE_URL") or "").strip()  # Embedding API地址
EMBEDDING_MODEL = str(os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5").strip()    # Embedding模型名称  
EMBEDDING_DEVICE = str(os.getenv("EMBEDDING_DEVICE") or "cuda").strip() or "cuda"

# ========== MinerU 配置 ==========
MINERU_BIN = str(os.getenv("MINERU_BIN") or "/home/naviai/miniconda3/envs/py310/bin/mineru").strip()
MINERU_BACKEND = str(os.getenv("MINERU_BACKEND") or "vlm-auto-engine").strip() or "vlm-auto-engine"
MINERU_MODEL_SOURCE = str(os.getenv("MINERU_MODEL_SOURCE") or "local").strip() or "local"
MINERU_OUTPUT_DIR = str(os.getenv("MINERU_OUTPUT_DIR") or "./data/raw/mineru").strip() or "./data/raw/mineru"
MINERU_TIMEOUT_SECONDS = int(str(os.getenv("MINERU_TIMEOUT_SECONDS") or "600").strip() or "600")
MINERU_API_URL = str(os.getenv("MINERU_API_URL") or "").strip()
MINERU_PTXAS_PATH = str(os.getenv("MINERU_PTXAS_PATH") or "/usr/local/cuda/bin/ptxas").strip() or "/usr/local/cuda/bin/ptxas"
MINERU_SERVER_URL = str(os.getenv("MINERU_SERVER_URL") or "").strip()

# ========== 文本切分配置 ==========
CHUNK_SIZE = 512      # 每个文本块的最大字符数
CHUNK_OVERLAP = 50    # 相邻文本块之间的重叠字符数（保持语义连贯）

# ========== 检索配置 ==========
TOP_K = 4                               # 检索时返回最相似的 Top-K 个文档块
MAX_RETRIEVAL_ROUNDS = 3                # 检索-生成最多循环轮数
LOW_CONFIDENCE_THRESHOLD = 0.45         # 低于该证据置信度时进入人工审核
ENABLE_RETRIEVAL_CONVERSATION_HISTORY = False
ENABLE_HYDE_QUERY_REWRITE = False
ENABLE_MEMORY_CONTEXT = False
ENABLE_LLM_CLASSIFICATION = False
ENABLE_RERANKER = False
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"  # 重排模型名称
RERANKER_DEVICE = "auto"                    # 重排模型运行设备: "auto"、"cuda" 或 "cpu"
RERANKER_MAX_CANDIDATES = 5                 # 重排最多处理的候选数
ENABLE_VECTOR_QUERY_VARIANTS = False

# ========== 调试显示配置 ==========
SHOW_CHUNK_CONTENT = str(os.getenv("SHOW_CHUNK_CONTENT") or "").strip().lower() in {"1", "true", "yes", "on"}

APP_HOST = "0.0.0.0"
APP_PORT = 8005
APP_EDITION = normalize_app_edition("server")
IS_ROBOT_EDITION = APP_EDITION == "robot"

STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
LOCAL_MODULE_DIR = BASE_DIR / "module"
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
RUNTIME_DIR = BASE_DIR / ".runtime"
DOCS_DIR = BASE_DIR / "doc"
QUESTION_COLLECTION_PATH = DATA_DIR / "chat" / "collected_questions.txt"
VECTOR_DB_DIR = DATA_DIR / "vectorstore"
WORKFLOWS_DIR = BASE_DIR / "workflows"
FAULT_WORKFLOWS_DIR = WORKFLOWS_DIR / "fault"
NORMAL_WORKFLOWS_DIR = WORKFLOWS_DIR / "normal"
FAULT_PLAYBOOKS_PATH = FAULT_WORKFLOWS_DIR
NORMAL_WORKFLOWS_PATH = NORMAL_WORKFLOWS_DIR
FAULT_PLAYBOOK_RULES_FILENAME = "rules.yaml"
DB_PATH = DATA_DIR / "operations.db"
CONNECTION_CACHE_PATH = DATA_DIR / "connection_cache.json"
DEPLOY_CONFIG_PATH = STATIC_DIR / "page_configs" / "deploy.json"
TRACE_LOG_PATH = RUNTIME_DIR / "runtime_trace.log"
FAULT_TRACE_LOG_PATH = TRACE_LOG_PATH
RUNTIME_TRACE_ENABLED = False
SESSION_COOKIE = "robot_upgrade_sid"
MAX_CONNECTION_CACHE_ITEMS = 8
MAX_TASK_ITEMS = 5
SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60
SESSION_CLEANUP_INTERVAL_SECONDS = 60

PACKAGE_DEPLOY_DIR = "/tmp"
MODULE_DEPLOY_ROOT = "/home/naviai/navi_project/.dists"
MODULE_DEPLOY_PROJECT_ROOT = "/home/naviai/navi_project"
ROS_COMPOSE_PROJECT_ROOT = "/home/naviai/navi_project"
ROSBRIDGE_SERVICE_NAME = "rosbridge"
MODULE_DEPLOY_NAMES = [
    "chassis",
    "perception",
    "sensor_lidar",
    "navigation",
    "map_server",
    "nviz",
]
DOWNLOAD_TMP_DIR = Path("/tmp")
CHFS_HOST = "10.51.33.211"
CHFS_PORT = 10000
CHFS_USER = "admin"
CHFS_PASSWORD = "admin"
UPLOAD_CHUNK_SIZE = 1024 * 1024
DEFAULT_DEPLOY_PAGE_CONFIG = {
    "package": {
        "rollback_template": "",
        "machine_options": [
            {"value": "H1",         "label": "H1",},
            {"value": "U1",         "label": "U1",},
            {"value": "U2_WA1",     "label": "U2_WA1",},
            {"value": "I2",         "label": "I2",},
            {"value": "WA1",        "label": "WA1",},
            {"value": "WA1_400L",   "label": "WA1_400L",},
            {"value": "WA1_400K",   "label": "WA1_400K",},
            {"value": "WA2",        "label": "WA2",},
            {"value": "WA2_LS",     "label": "WA2_LS",},
            {"value": "WA2_TY20",   "label": "WA2_TY20",},
            {"value": "WA2_L",      "label": "WA2_L",},
            {"value": "U1_WA1",     "label": "U1_WA1",},
        ],
    },
    "module": {
        "machine_options": [
            {
                "value": module_name,
                "label": module_name,
            }
            for module_name in MODULE_DEPLOY_NAMES
        ],
    },
}
PROJECT_ROOT_CANDIDATES = [
    ("/home/naviai/navi_project", "项目目录 /home/naviai/navi_project"),
    ("~/navi_project", "机器人 ~/navi_project"),
]
LEGACY_DB_PATH = BASE_DIR / "operations.db"
LEGACY_CONNECTION_CACHE_PATH = BASE_DIR / "connection_cache.json"
