from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgeDocument:
    doc_id: str  # 文档唯一 ID
    source: str  # 原始文件路径
    filename: str  # 文件名
    filetype: str  # 文件类型，如 md/pdf/docx/txt
    content: str  # 文档清洗后的完整文本
    loader: str = ""  # 使用的加载器，如 text/mineru


@dataclass
class KnowledgeChunk:
    chunk_id: str  # 切片唯一 ID
    doc_id: str  # 所属文档 ID
    content: str  # 切片文本
    title_path: list[str] = field(default_factory=list)  # 标题层级路径
    metadata: dict[str, Any] = field(default_factory=dict)  # 附加元数据


@dataclass
class EmbeddingSpec:
    provider: str  # embedding 提供方
    model: str  # embedding 模型名
    base_url: str = ""  # embedding 服务地址


@dataclass
class VectorRecord:
    chunk_id: str  # 对应切片 ID
    embedding: list[float] = field(default_factory=list)  # 向量值
    metadata: dict[str, Any] = field(default_factory=dict)  # 向量记录元数据


@dataclass
class RetrievalRequest:
    query: str = ""  # 检索查询文本
    top_k: int = 0  # 召回数量
    channels: list[str] = field(default_factory=list)  # 检索通道，如 faq/bm25/vector


@dataclass
class RetrievalHit:
    chunk_id: str = ""  # 命中的切片 ID
    filename: str = ""  # 来源文件名
    score: float = 0.0  # 检索得分
    snippet: str = ""  # 命中文本片段
    channel: str = ""  # 来源检索通道


@dataclass
class RetrievalResult:
    query: str = ""  # 原始查询
    hits: list[RetrievalHit] = field(default_factory=list)  # 命中结果
    context: str = ""  # 拼接后的检索上下文
    confidence: float = 0.0  # 检索置信度
    low_confidence: bool = False  # 是否低置信度
