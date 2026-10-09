from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from api.app import _notify_feishu_async, _run_automation_consumer_once, _run_template_seed_prewarm_once
from automation.job_queue import HuntJobQueue


@pytest.mark.asyncio
async def test_embedded_consumer_claims_and_completes_job(monkeypatch, tmp_path):
    queue_path = str(tmp_path / "queue.db")
    queue = HuntJobQueue(queue_path)
    queue.init_db()
    job_id = queue.enqueue(
        {"website_url": "https://www.gdushun.com/", "description": "Find distributors"},
        now_iso="2026-04-05T00:00:00+00:00",
    )

    settings = type(
        "S",
        (),
        {
            "automation_queue_db_path": queue_path,
            "automation_consumer_auto_start_campaign": True,
            "automation_consumer_status_poll_seconds": 15,
            "automation_consumer_request_timeout_seconds": 60,
            "automation_consumer_retry_delay_seconds": 120,
            "automation_consumer_poll_seconds": 5,
            "automation_embedded_consumer_enabled": True,
            "api_host": "127.0.0.1",
            "api_port": 8000,
            "api_access_token": "",
        },
    )()
    monkeypatch.setattr("api.app.get_settings", lambda: settings)
    monkeypatch.setattr(
        "api.app._run_embedded_consumer_job",
        AsyncMock(return_value={"hunt_id": "hunt-embedded", "lead_count": 3, "email_sequence_count": 2, "campaign": None}),
    )

    assert await _run_automation_consumer_once() is True
    job = queue.get(job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert job["last_hunt_id"] == "hunt-embedded"
    assert job["progress_stage"] == "completed"


@pytest.mark.asyncio
async def test_embedded_consumer_stops_cancelled_job(monkeypatch, tmp_path):
    from scripts.headless_worker import JobCancelledError

    queue_path = str(tmp_path / "queue.db")
    queue = HuntJobQueue(queue_path)
    queue.init_db()
    job_id = queue.enqueue(
        {"website_url": "https://www.gdushun.com/", "description": "Find distributors"},
        now_iso="2026-04-05T00:00:00+00:00",
    )

    settings = type(
        "S",
        (),
        {
            "automation_queue_db_path": queue_path,
            "automation_consumer_auto_start_campaign": True,
            "automation_consumer_status_poll_seconds": 15,
            "automation_consumer_request_timeout_seconds": 60,
            "automation_consumer_retry_delay_seconds": 120,
            "automation_consumer_poll_seconds": 5,
            "automation_embedded_consumer_enabled": True,
            "api_host": "127.0.0.1",
            "api_port": 8000,
            "api_access_token": "",
        },
    )()
    monkeypatch.setattr("api.app.get_settings", lambda: settings)

    async def fake_run_hunt_payload(args, payload):
        queue.cancel(job_id, updated_at="2026-04-05T00:01:00+00:00")
        raise JobCancelledError("Queue job cancelled by user")

    monkeypatch.setattr("api.app._run_embedded_consumer_job", fake_run_hunt_payload)
    requested: list[tuple[str, str]] = []
    monkeypatch.setattr("api.app.request_hunt_cancel", lambda hunt_id, reason="": requested.append((hunt_id, reason)) or True)

    assert await _run_automation_consumer_once() is True
    job = queue.get(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert job["progress_stage"] == "cancelled"
    assert requested == []


@pytest.mark.asyncio
async def test_template_seed_worker_prewarms_queued_job(monkeypatch, tmp_path):
    queue_path = str(tmp_path / "queue.db")
    queue = HuntJobQueue(queue_path)
    queue.init_db()
    job_id = queue.enqueue(
        {
            "website_url": "https://www.gdushun.com/",
            "description": "Find distributors",
            "product_keywords": ["micro switch"],
            "target_regions": ["United States"],
            "enable_email_craft": True,
        },
        now_iso="2026-04-05T00:00:00+00:00",
    )

    settings = type(
        "S",
        (),
        {
            "automation_queue_db_path": queue_path,
            "automation_template_seed_prewarm_enabled": True,
            "automation_consumer_poll_seconds": 5,
        },
    )()
    monkeypatch.setattr("api.app.get_settings", lambda: settings)
    monkeypatch.setattr(
        "api.app._prepare_template_seed",
        AsyncMock(return_value={"source": "pre_generated", "template_profile": {}, "template_plan": {}}),
    )

    assert await _run_template_seed_prewarm_once() is True
    job = queue.get(job_id)
    assert job is not None
    assert job["template_seed_status"] == "ready"
    assert job["template_seed_source"] == "pre_generated"
    assert isinstance(job["payload"]["template_seed"], dict)


@pytest.mark.asyncio
async def test_embedded_consumer_offloads_feishu_notifications(monkeypatch):
    monkeypatch.setattr("api.app.send_feishu_text", lambda webhook, text: {"ok": True})
    monkeypatch.setattr("api.app.get_settings", lambda: type("S", (), {"automation_feishu_webhook_url": "https://feishu.test/hook"})())

    called: list[tuple] = []

    async def fake_to_thread(func, *args, **kwargs):
        called.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr("api.app.asyncio.to_thread", fake_to_thread)
    await _notify_feishu_async("hello")

    assert called
    assert "hello" in called[0][1]
