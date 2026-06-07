"""知识库导入链路。"""

from .loader import SUPPORTED_FILE_SUFFIXES, load_documents
from .splitter import split_documents

__all__ = [
    "SUPPORTED_FILE_SUFFIXES",
    "load_documents",
    "split_documents",
]
