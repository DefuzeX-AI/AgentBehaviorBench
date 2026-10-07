"""Dedicated WebSocket traffic logging."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

_WS_LOGGER_NAMES = (
    "app.modules.realtime",
    "app.modules.realtime.manager",
    "app.modules.realtime.router",
)

_configured = False


def format_ws_payload(payload: Any, *, max_chars: int | None = None) -> str:
    """Serialize a WebSocket payload for logs, truncating long strings (e.g. base64)."""

    settings = get_settings()
    limit = max_chars if max_chars is not None else settings.ws_log_body_max_chars

    def _sanitize(value: Any, depth: int = 0) -> Any:
        if depth > 12:
            return "..."
        if isinstance(value, str):
            if len(value) <= 256:
                return value
            return f"{value[:128]}...<{len(value)} chars>"
        if isinstance(value, dict):
            return {str(k): _sanitize(v, depth + 1) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_sanitize(item, depth + 1) for item in value]
        return value

    try:
        text = json.dumps(_sanitize(payload), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(payload)

    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<{len(text)} chars>"


def setup_websocket_logging(settings: Settings | None = None) -> None:
    """Attach a rotating file handler for all WebSocket send/receive logs."""

    global _configured
    settings = settings or get_settings()
    if not settings.ws_log_enabled:
        return

    log_path = Path(settings.ws_log_file)
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level_name = str(settings.ws_log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=int(settings.ws_log_max_bytes),
        backupCount=int(settings.ws_log_backup_count),
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.setLevel(level)

    for name in _WS_LOGGER_NAMES:
        ws_logger = logging.getLogger(name)
        ws_logger.handlers = [
            existing for existing in ws_logger.handlers if not isinstance(existing, RotatingFileHandler)
        ]
        ws_logger.setLevel(level)
        ws_logger.addHandler(handler)
        ws_logger.propagate = False

    _configured = True
