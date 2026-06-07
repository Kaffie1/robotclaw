from __future__ import annotations

from time import perf_counter
from typing import Any

from ...core.shared import append_fault_trace, logger


def start_stage_timer() -> float:
    return perf_counter()


def log_stage_duration(stage: str, started_at: float, **payload: Any) -> float:
    duration_ms = round((perf_counter() - started_at) * 1000, 1)
    logger.info("阶段耗时 | stage=%s | duration_ms=%.1f", stage, duration_ms)
    trace_payload: dict[str, Any] = {"stage": stage, "duration_ms": duration_ms}
    if payload:
        trace_payload.update(payload)
    append_fault_trace("stage_timing", trace_payload)
    return duration_ms


__all__ = ["log_stage_duration", "start_stage_timer"]
