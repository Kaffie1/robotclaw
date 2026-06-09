"""Embedding 模型工厂。

职责保持简单：
- provider/model 解析
- embedding 实例缓存
- 本机默认设备自动探测
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from ..shared.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
)

def _embedding_provider() -> str:
    return EMBEDDING_PROVIDER


def _embedding_model() -> str:
    return EMBEDDING_MODEL


def _embedding_base_url() -> str:
    return EMBEDDING_BASE_URL


def _embedding_api_key() -> str:
    return EMBEDDING_API_KEY


def _configured_embedding_device() -> str:
    return str(EMBEDDING_DEVICE or "").strip().lower()


def _embedding_device() -> str:
    configured = _configured_embedding_device()
    if configured and configured != "auto":
        return configured
    try:
        import torch
    except ImportError:
        return "cpu"
    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _should_disable_openai_length_check(base_url: str) -> bool:
    normalized = (base_url or "").strip()
    if not normalized:
        return False
    hostname = (urlparse(normalized).hostname or "").lower()
    if not hostname:
        return False
    return hostname not in {"api.openai.com"}


def _resolve_local_huggingface_model_path(model_name: str) -> str | None:
    normalized = (model_name or "").strip()
    if not normalized:
        return None

    expanded = Path(normalized).expanduser()
    if expanded.exists():
        return str(expanded)

    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None

    for filename in ("modules.json", "config.json", "tokenizer_config.json"):
        try:
            cached = try_to_load_from_cache(repo_id=normalized, filename=filename)
        except Exception:
            return None
        if isinstance(cached, str):
            return str(Path(cached).parent)
    return None


@lru_cache(maxsize=4)
def _build_huggingface_embeddings(model_name: str, device: str):
    from langchain_huggingface import HuggingFaceEmbeddings

    resolved_model_name = _resolve_local_huggingface_model_path(model_name) or model_name
    model_kwargs = {"device": device}
    if resolved_model_name != model_name:
        model_kwargs["local_files_only"] = True
    return HuggingFaceEmbeddings(
        model_name=resolved_model_name,
        model_kwargs=model_kwargs,
    )


@lru_cache(maxsize=4)
def _build_openai_embeddings(model: str, api_key: str, base_url: str):
    from langchain_openai import OpenAIEmbeddings

    kwargs = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }
    if _should_disable_openai_length_check(base_url):
        kwargs.update(
            {
                "check_embedding_ctx_length": False,
                "model_kwargs": {"encoding_format": "float"},
            }
        )
    return OpenAIEmbeddings(**kwargs)


def clear_embeddings_cache() -> None:
    _build_huggingface_embeddings.cache_clear()
    _build_openai_embeddings.cache_clear()


def get_embeddings():
    provider = _embedding_provider()
    model = _embedding_model()

    if provider == "huggingface":
        runtime_device = _embedding_device()
        try:
            return _build_huggingface_embeddings(model, runtime_device)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize HuggingFace embedding model "
                f"'{model}' on device '{runtime_device}': {exc}"
            ) from exc

    api_key = _embedding_api_key()
    if not api_key:
        raise RuntimeError("知识检索未配置 EMBEDDING_API_KEY/OPENAI_API_KEY，无法初始化 embedding 模型。")
    return _build_openai_embeddings(model, api_key, _embedding_base_url())
