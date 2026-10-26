"""Tests for Web history helpers."""

from __future__ import annotations

import json
import threading

from web import history


def test_incomplete_task_round_trip(tmp_path, monkeypatch):
    index = tmp_path / "incomplete_tasks.json"
    logs = tmp_path / "logs"
    monkeypatch.setattr(history, "_INCOMPLETE_TASKS_FILE", index)
    monkeypatch.setattr(history, "_results_dir", lambda: logs)
    monkeypatch.setattr(history, "_checkpoint_step", lambda ticker, trade_date: 3)

    history.record_incomplete_task(
        "600370",
        "2026-06-02",
        status="error",
        error="quota exceeded",
        completed_stages=["market", "news"],
    )

    entries = history.get_incomplete_history()

    assert entries == [
        {
            "ticker": "600370",
            "trade_date": "2026-06-02",
            "status": "error",
            "error": "quota exceeded",
            "completed_stages": ["market", "news"],
            "updated_at": entries[0]["updated_at"],
            "checkpoint_step": 3,
        }
    ]


def test_completed_history_hides_incomplete_task(tmp_path, monkeypatch):
    index = tmp_path / "incomplete_tasks.json"
    logs = tmp_path / "logs"
    log_dir = logs / "600370" / "TradingAgentsStrategy_logs"
    log_dir.mkdir(parents=True)
    (log_dir / "full_states_log_2026-06-02.json").write_text(
        json.dumps({"final_trade_decision": "HOLD"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(history, "_INCOMPLETE_TASKS_FILE", index)
    monkeypatch.setattr(history, "_results_dir", lambda: logs)
    monkeypatch.setattr(history, "_checkpoint_step", lambda ticker, trade_date: 3)

    history.record_incomplete_task("600370", "2026-06-02", status="running")

    assert history.get_incomplete_history() == []


def test_incomplete_task_writes_are_thread_safe(tmp_path, monkeypatch):
    index = tmp_path / "incomplete_tasks.json"
    logs = tmp_path / "logs"
    monkeypatch.setattr(history, "_INCOMPLETE_TASKS_FILE", index)
    monkeypatch.setattr(history, "_results_dir", lambda: logs)
    monkeypatch.setattr(history, "_checkpoint_step", lambda ticker, trade_date: 1)

    def write_task(i: int) -> None:
        history.record_incomplete_task(
            f"60037{i % 10}",
            "2026-06-02",
            status="running",
            completed_stages=["market"],
        )

    threads = [threading.Thread(target=write_task, args=(i,)) for i in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    entries = history.get_incomplete_history()

    assert len(entries) == 10
    assert {entry["status"] for entry in entries} == {"running"}
    assert not list(tmp_path.glob("*.tmp"))


def test_extract_signal_chinese_final_decision():
    """Chinese free-text decision must yield the real rating, not Hold/N/A.

    Regression for issues #78 / #80: history reload used an English-only
    BUY/SELL/HOLD scan that missed Chinese output entirely.
    """
    state = {
        "final_trade_decision": "最终评级：卖出\n核心结论：风险尚未出清。",
        "investment_plan": "研究经理倾向持有观望。",
    }
    assert history.extract_signal(state) == "Sell"


def test_extract_signal_prefers_final_trade_decision():
    """The reload signal must match the authoritative live signal source."""
    state = {
        "investment_plan": "最终评级：买入",
        "final_trade_decision": "最终评级：减持",
    }
    assert history.extract_signal(state) == "Underweight"


def test_extract_signal_english_still_works():
    state = {"final_trade_decision": "**Rating**: Buy\n\nThesis."}
    assert history.extract_signal(state) == "Buy"


def test_extract_signal_unknown_returns_na():
    assert history.extract_signal({"final_trade_decision": "无明确方向。"}) == "N/A"
    assert history.extract_signal({}) == "N/A"
