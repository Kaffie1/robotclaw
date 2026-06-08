from __future__ import annotations

import logging
from pathlib import Path


_LOGGER_INITIALIZED = False
_LOG_FILE_PATH = Path(".runtime/runtime.log")


def setup_logging(root_dir: Path, *, level: int = logging.INFO, log_filename: str = "runtime.log") -> Path:
    global _LOGGER_INITIALIZED, _LOG_FILE_PATH

    runtime_dir = root_dir / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = runtime_dir / log_filename

    if _LOGGER_INITIALIZED and _LOG_FILE_PATH == log_file_path:
        logging.getLogger("robotclaw").setLevel(level)
        return log_file_path

    logger = logging.getLogger("robotclaw")
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _LOGGER_INITIALIZED = True
    _LOG_FILE_PATH = log_file_path
    return log_file_path


def get_logger(name: str) -> logging.Logger:
    logger_name = f"robotclaw.{name.strip()}" if name.strip() else "robotclaw"
    return logging.getLogger(logger_name)
