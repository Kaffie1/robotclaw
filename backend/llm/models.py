from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


LLMRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class LLMMessage:
    role: LLMRole
    content: str | list[dict[str, Any]]


@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    model: str
    content: str
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredLLMResponse:
    model: str
    content: str
    parsed: dict[str, Any]
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioTranscriptionResponse:
    model: str
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
