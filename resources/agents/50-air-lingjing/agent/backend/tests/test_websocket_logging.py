"""Tests for dedicated WebSocket traffic logging."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.logging import format_ws_payload, setup_websocket_logging
from app.modules.realtime.manager import RealtimeManager


def test_format_ws_payload_truncates_long_strings():
    payload = {"camera_rgb": "A" * 500, "pose": {"x": 1.0}}
    text = format_ws_payload(payload, max_chars=2000)
    assert "500 chars" in text
    assert '"x": 1.0' in text


def test_setup_websocket_logging_writes_to_file(tmp_path: Path, monkeypatch):
    import app.core.logging as core_logging

    core_logging._configured = False
    log_file = tmp_path / "websocket.log"
    settings = Settings(
        ws_log_enabled=True,
        ws_log_file=str(log_file),
        ws_log_level="INFO",
    )
    monkeypatch.setattr("app.core.logging.get_settings", lambda: settings)

    setup_websocket_logging(settings)

    ws_logger = logging.getLogger("app.modules.realtime.manager")
    ws_logger.info("test websocket log line")

    for handler in ws_logger.handlers:
        handler.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "test websocket log line" in content


def test_handle_message_logs_inbound_json(tmp_path: Path, monkeypatch):
    import app.core.logging as core_logging

    core_logging._configured = False
    log_file = tmp_path / "websocket.log"
    settings = Settings(
        ws_log_enabled=True,
        ws_log_file=str(log_file),
        ws_log_level="INFO",
    )
    monkeypatch.setattr("app.core.logging.get_settings", lambda: settings)
    setup_websocket_logging(settings)

    manager = RealtimeManager()
    monkeypatch.setattr(manager, "persist_task_data", lambda *args, **kwargs: None)

    async def _run() -> None:
        await manager.handle_message(
            "LJ-ENGINE_demo",
            json.dumps(
                {
                    "commandType": "pushEngineTelemetry",
                    "taskId": "task-1",
                    "data": {"frame": 1},
                }
            ),
        )

    asyncio.run(_run())

    for handler in logging.getLogger("app.modules.realtime.manager").handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "IN session=LJ-ENGINE_demo" in content
    assert "pushEngineTelemetry" in content
    assert "task-1" in content


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


def test_send_by_user_type_logs_outbound(tmp_path: Path, monkeypatch):
    import app.core.logging as core_logging

    core_logging._configured = False
    log_file = tmp_path / "websocket.log"
    settings = Settings(
        ws_log_enabled=True,
        ws_log_file=str(log_file),
        ws_log_level="INFO",
    )
    monkeypatch.setattr("app.core.logging.get_settings", lambda: settings)
    setup_websocket_logging(settings)

    manager = RealtimeManager()
    ws = _FakeWebSocket()
    session_key = "LJ-UE_demo"
    manager.session_map["LJ-UE"][session_key] = ws
    manager.session_key_map[session_key] = ws

    async def _run() -> None:
        await manager.send_by_user_type({"type": "DATA", "data": {"foo": 1}}, "LJ-UE")

    asyncio.run(_run())

    for handler in logging.getLogger("app.modules.realtime.manager").handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert f"OUT session={session_key}" in content
    assert "broadcast_user_type" in content
    assert ws.sent
