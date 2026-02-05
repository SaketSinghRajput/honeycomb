from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from app.core.config import settings

try:
    from colorlog import ColoredFormatter
except Exception:  # pragma: no cover - optional dependency
    ColoredFormatter = None


_LOGGER_LOCK = threading.Lock()
_LOGGER_CONFIGURED = False


def _ensure_log_dir() -> Path:
    logs_dir = Path(__file__).resolve().parents[2] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _build_formatter():
    log_format = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    if ColoredFormatter:
        return ColoredFormatter(
            "%(log_color)s" + log_format,
            datefmt=date_format,
            reset=True,
        )

    return logging.Formatter(log_format, datefmt=date_format)


def _configure_root_logger():
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    with _LOGGER_LOCK:
        if _LOGGER_CONFIGURED:
            return

        root_logger = logging.getLogger()
        root_logger.setLevel(settings.LOG_LEVEL)

        formatter = _build_formatter()

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        logs_dir = _ensure_log_dir()
        file_handler = logging.FileHandler(logs_dir / "app.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(file_handler)

        _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root_logger()
    return logging.getLogger(name)


def log_model_load(model_name: str, path: Optional[str] = None) -> None:
    logger = get_logger("models.loader")
    if path:
        logger.info("Loaded model %s from %s", model_name, path)
    else:
        logger.info("Loaded model %s", model_name)


def log_api_request(method: str, path: str, status_code: int, duration_ms: int) -> None:
    logger = get_logger("api.request")
    logger.info("%s %s -> %s (%sms)", method, path, status_code, duration_ms)


def log_error(message: str, exc: Optional[Exception] = None) -> None:
    logger = get_logger("app.error")
    if exc:
        logger.exception("%s", message)
    else:
        logger.error("%s", message)
