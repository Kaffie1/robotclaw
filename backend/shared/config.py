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


# ========== OpenAI API 配置 ==========
OPENAI_API_KEY = str(os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_BASE_URL = str(os.getenv("OPENAI_BASE_URL") or "").strip()
OPENAI_CHAT_MODEL = str(os.getenv("OPENAI_CHAT_MODEL") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
OPENAI_CHAT_TEMPERATURE = float(str(os.getenv("OPENAI_CHAT_TEMPERATURE") or "0.2").strip() or "0.2")
OPENAI_ENABLE_REASONING_SPLIT = str(os.getenv("OPENAI_ENABLE_REASONING_SPLIT") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OPENAI_THINK = str(os.getenv("OPENAI_THINK") or "").strip()

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

# ========== 文本切分配置 ==========
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# ========== 检索配置 ==========
TOP_K = 4
LOW_CONFIDENCE_THRESHOLD = 0.45
RERANKER_MAX_CANDIDATES = 5

# ========== 调试显示配置 ==========
SHOW_CHUNK_CONTENT = str(os.getenv("SHOW_CHUNK_CONTENT") or "").strip().lower() in {"1", "true", "yes", "on"}
