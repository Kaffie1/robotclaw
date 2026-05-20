import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import TRACE_LOG_PATH


def setup_runtime_logger() -> logging.Logger:
    logger = logging.getLogger("runtime")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    log_path = Path(TRACE_LOG_PATH).parent / "runtime.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class PrettyTraceFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        raw_message = super().format(record)
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return raw_message
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def setup_runtime_trace_logger() -> logging.Logger:
    logger = logging.getLogger("runtime.trace")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    log_path = Path(TRACE_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PrettyTraceFormatter("%(message)s"))

    logger.addHandler(file_handler)
    return logger


_runtime_logger: logging.Logger | None = None


def get_runtime_logger() -> logging.Logger:
    global _runtime_logger
    if _runtime_logger is None:
        _runtime_logger = setup_runtime_logger()
    return _runtime_logger


_runtime_trace_logger: logging.Logger | None = None


def get_runtime_trace_logger() -> logging.Logger:
    global _runtime_trace_logger
    if _runtime_trace_logger is None:
        _runtime_trace_logger = setup_runtime_trace_logger()
    return _runtime_trace_logger


logger = get_runtime_logger()
trace_logger = get_runtime_trace_logger()


def truncate_trace_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, dict):
        normalized_keys = {str(key) for key in value.keys()}
        if normalized_keys and normalized_keys <= {"label", "value"}:
            items: dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(item, str):
                    items[str(key)] = item if len(item) <= 200 else f"{item[:200]}…(truncated,{len(item)} chars)"
                else:
                    items[str(key)] = truncate_trace_value(item, depth=depth + 1)
            return items
    if depth >= 4:
        return "…"
    if isinstance(value, dict):
        items: dict[str, Any] = {}
        for key, item in list(value.items())[:60]:
            items[str(key)] = truncate_trace_value(item, depth=depth + 1)
        return items
    if isinstance(value, list):
        return [truncate_trace_value(item, depth=depth + 1) for item in value[:60]]
    if isinstance(value, str):
        if len(value) <= 4000:
            return value
        return f"{value[:4000]}…(truncated,{len(value)} chars)"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def append_runtime_trace(event: str, payload: dict[str, Any]) -> None:
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "payload": truncate_trace_value(payload),
    }
    trace_logger.info(json.dumps(record, ensure_ascii=False))


def setup_fault_logger() -> logging.Logger:
    return setup_runtime_logger()


def setup_fault_trace_logger() -> logging.Logger:
    return setup_runtime_trace_logger()


def get_fault_logger() -> logging.Logger:
    return get_runtime_logger()


def get_fault_trace_logger() -> logging.Logger:
    return get_runtime_trace_logger()


def append_fault_trace(event: str, payload: dict[str, Any]) -> None:
    append_runtime_trace(event, payload)
