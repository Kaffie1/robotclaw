"""Embedding 模型工厂。

先沿用上级 knowledge 项目的职责边界：
- provider/model/device 解析
- embedding 实例缓存
- runtime device override

当前仓库还没接入知识库配置，因此这里保持 import-safe，
只有真正调用时才按配置解析 provider 并尝试构建模型。
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import urlparse

_EMBEDDING_DEVICE_OVERRIDE: str | None = None


def _embedding_provider() -> str:
    return str(os.getenv("EMBEDDING_PROVIDER") or "openai").strip().lower() or "openai"


def _embedding_model() -> str:
    return str(os.getenv("EMBEDDING_MODEL") or "text-embedding-3-large").strip() or "text-embedding-3-large"


def _embedding_base_url() -> str:
    return str(os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()


def _embedding_api_key() -> str:
    return str(os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _embedding_device() -> str:
    return str(os.getenv("EMBEDDING_DEVICE") or "cpu").strip() or "cpu"


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


def set_embedding_device_override(device: str | None) -> None:
    global _EMBEDDING_DEVICE_OVERRIDE
    if _EMBEDDING_DEVICE_OVERRIDE == device:
        return
    _EMBEDDING_DEVICE_OVERRIDE = device
    clear_embeddings_cache()


def get_embeddings():
    provider = _embedding_provider()
    model = _embedding_model()

    if provider == "huggingface":
        runtime_device = _EMBEDDING_DEVICE_OVERRIDE or _embedding_device()
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
