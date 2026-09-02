from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class LLMCallMetric:
    provider: str
    profile_id: str
    model: str
    node: str = ""
    duration_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class LLMMetricCollector:
    calls: list[LLMCallMetric] = field(default_factory=list)


_CURRENT_COLLECTOR: ContextVar[LLMMetricCollector | None] = ContextVar("llm_metric_collector", default=None)


@contextmanager
def collect_llm_metrics() -> Iterator[LLMMetricCollector]:
    collector = LLMMetricCollector()
    token = _CURRENT_COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _CURRENT_COLLECTOR.reset(token)


def record_llm_call(metric: LLMCallMetric) -> None:
    collector = _CURRENT_COLLECTOR.get()
    if collector is not None:
        collector.calls.append(metric)


def summarize_llm_metrics(collector: LLMMetricCollector) -> dict[str, Any]:
    calls = list(collector.calls)
    known_total_tokens = [item.total_tokens for item in calls if item.total_tokens is not None]
    known_input_tokens = [item.input_tokens for item in calls if item.input_tokens is not None]
    known_output_tokens = [item.output_tokens for item in calls if item.output_tokens is not None]
    return {
        "llm_call_count": len(calls),
        "llm_duration_ms": sum(max(0, item.duration_ms) for item in calls),
        "input_tokens": sum(known_input_tokens) if known_input_tokens else None,
        "output_tokens": sum(known_output_tokens) if known_output_tokens else None,
        "total_tokens": sum(known_total_tokens) if known_total_tokens else None,
        "calls": [
            {
                "provider": item.provider,
                "profile_id": item.profile_id,
                "model": item.model,
                "node": item.node,
                "duration_ms": item.duration_ms,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "total_tokens": item.total_tokens,
            }
            for item in calls
        ],
    }
