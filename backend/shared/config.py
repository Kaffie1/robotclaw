from __future__ import annotations

import os
from pathlib import Path

from .env import load_env_file


BASE_DIR = Path(__file__).resolve().parents[2]
load_env_file(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
RUNTIME_DIR = BASE_DIR / ".runtime"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
VECTOR_DB_DIR = DATA_DIR / "vectorstore"


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# ========== OpenAI API 配置 ==========
OPENAI_API_KEY = str(os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_BASE_URL = str(os.getenv("OPENAI_BASE_URL") or "").strip()
OPENAI_CHAT_MODEL = str(os.getenv("OPENAI_CHAT_MODEL") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
OPENAI_CHAT_TEMPERATURE = float(str(os.getenv("OPENAI_CHAT_TEMPERATURE") or "0.2").strip() or "0.2")
OPENAI_ENABLE_REASONING_SPLIT = _env_bool("OPENAI_ENABLE_REASONING_SPLIT", False)
OPENAI_THINK = str(os.getenv("OPENAI_THINK") or "").strip()
OPENAI_ASR_MODEL = str(os.getenv("OPENAI_ASR_MODEL") or "").strip()

# ========== LLM 配置 ==========
LLM_PROVIDER = str(os.getenv("LLM_PROVIDER") or "openai").strip() or "openai"
LLM_MODEL = str(os.getenv("LLM_MODEL") or "").strip()
LLM_ASR_PROVIDER = str(os.getenv("LLM_ASR_PROVIDER") or "").strip()
LLM_ASR_MODEL = str(os.getenv("LLM_ASR_MODEL") or "").strip()
LLM_ASR_LANGUAGE = str(os.getenv("LLM_ASR_LANGUAGE") or "zh").strip() or "zh"
LLM_TEMPERATURE = float(str(os.getenv("LLM_TEMPERATURE") or "0").strip() or "0")
LLM_MAX_TOKENS = int(str(os.getenv("LLM_MAX_TOKENS") or "1024").strip() or "1024")
LLM_TIMEOUT = float(str(os.getenv("LLM_TIMEOUT") or "30").strip() or "30")
LLM_ASR_TIMEOUT = float(str(os.getenv("LLM_ASR_TIMEOUT") or "60").strip() or "60")
LLM_API_BASE = str(os.getenv("LLM_API_BASE") or "").strip()
LLM_API_KEY = str(os.getenv("LLM_API_KEY") or "").strip()
LLM_PROFILES = str(os.getenv("LLM_PROFILES") or "").strip()
LLM_ACTIVE_PROFILE = str(os.getenv("LLM_ACTIVE_PROFILE") or "").strip() or "default"

# ========== Embedding 配置 ==========
EMBEDDING_PROVIDER = str(os.getenv("EMBEDDING_PROVIDER") or "huggingface").strip() or "huggingface"
EMBEDDING_API_KEY = str(os.getenv("EMBEDDING_API_KEY") or "").strip()
EMBEDDING_BASE_URL = str(os.getenv("EMBEDDING_BASE_URL") or "").strip()
EMBEDDING_MODEL = str(os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5").strip() or "BAAI/bge-small-zh-v1.5"
EMBEDDING_DEVICE = str(os.getenv("EMBEDDING_DEVICE") or "cuda").strip() or "cuda"

# ========== MinerU 配置 ==========
MINERU_BIN = str(os.getenv("MINERU_BIN") or "mineru").strip() or "mineru"
MINERU_BACKEND = str(os.getenv("MINERU_BACKEND") or "vlm-auto-engine").strip() or "vlm-auto-engine"
MINERU_MODEL_SOURCE = str(os.getenv("MINERU_MODEL_SOURCE") or "local").strip() or "local"
MINERU_OUTPUT_DIR = str(os.getenv("MINERU_OUTPUT_DIR") or str(BASE_DIR / "data" / "raw" / "mineru")).strip()
MINERU_TIMEOUT_SECONDS = int(str(os.getenv("MINERU_TIMEOUT_SECONDS") or "600").strip() or "600")
MINERU_API_URL = str(os.getenv("MINERU_API_URL") or "").strip()
MINERU_PTXAS_PATH = str(os.getenv("MINERU_PTXAS_PATH") or "/usr/local/cuda/bin/ptxas").strip() or "/usr/local/cuda/bin/ptxas"
MINERU_SERVER_URL = str(os.getenv("MINERU_SERVER_URL") or "").strip()

# ========== 语音配置 ==========
SPEECH_AUTO_SEND = True

# ========== 会话模式配置 ==========
DEFAULT_INTERACTION_MODE = str(os.getenv("DEFAULT_INTERACTION_MODE") or "agent").strip().lower() or "agent"
if DEFAULT_INTERACTION_MODE not in {"playbook", "qa", "agent"}:
    DEFAULT_INTERACTION_MODE = "agent"

# ========== 火山 ASR 配置 ==========
VOLCENGINE_ASR_MODEL = str(os.getenv("VOLCENGINE_ASR_MODEL") or "").strip() or "bigmodel"
VOLCENGINE_ASR_LANGUAGE = str(os.getenv("VOLCENGINE_ASR_LANGUAGE") or "").strip() or "zh-CN"
VOLCENGINE_ASR_WS_URL = (
    str(os.getenv("VOLCENGINE_ASR_WS_URL") or "").strip()
    or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
)
VOLCENGINE_ASR_RESOURCE_ID = (
    str(os.getenv("VOLCENGINE_ASR_RESOURCE_ID") or "").strip() or "volc.bigasr.sauc.duration"
)
VOLCENGINE_ASR_API_KEY = str(os.getenv("VOLCENGINE_ASR_API_KEY") or "").strip()
VOLCENGINE_ASR_APP_KEY = str(os.getenv("VOLCENGINE_ASR_APP_KEY") or "").strip()
VOLCENGINE_ASR_ACCESS_KEY = str(os.getenv("VOLCENGINE_ASR_ACCESS_KEY") or "").strip()
VOLCENGINE_ASR_SEGMENT_DURATION = int(str(os.getenv("VOLCENGINE_ASR_SEGMENT_DURATION") or "200").strip() or "200")
VOLCENGINE_ASR_TIMEOUT = float(str(os.getenv("VOLCENGINE_ASR_TIMEOUT") or "60").strip() or "60")
VOLCENGINE_ASR_ENABLE_ITN = _env_bool("VOLCENGINE_ASR_ENABLE_ITN", True)
VOLCENGINE_ASR_ENABLE_PUNC = _env_bool("VOLCENGINE_ASR_ENABLE_PUNC", True)
VOLCENGINE_ASR_ENABLE_DDC = _env_bool("VOLCENGINE_ASR_ENABLE_DDC", True)
VOLCENGINE_ASR_SHOW_UTTERANCES = _env_bool("VOLCENGINE_ASR_SHOW_UTTERANCES", True)

# ========== 文本切分配置 ==========
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# ========== 检索配置 ==========
TOP_K = 4
LOW_CONFIDENCE_THRESHOLD = 0.45
RERANKER_MAX_CANDIDATES = 5

# ========== 调试显示配置 ==========
SHOW_CHUNK_CONTENT = _env_bool("SHOW_CHUNK_CONTENT", False)
