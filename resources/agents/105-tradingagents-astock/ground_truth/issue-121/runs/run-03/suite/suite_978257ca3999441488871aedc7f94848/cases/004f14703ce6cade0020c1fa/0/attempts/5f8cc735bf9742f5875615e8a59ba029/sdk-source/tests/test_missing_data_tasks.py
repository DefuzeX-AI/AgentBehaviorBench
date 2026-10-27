"""Tests for missing-data task recording and retry helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.dataflows import missing_data


@pytest.fixture()
def missing_index(tmp_path, monkeypatch):
    index = tmp_path / "missing_data_tasks.json"
    cache_dir = tmp_path / "missing_data_cache"
    monkeypatch.setattr(missing_data, "_MISSING_DATA_TASKS_FILE", index)
    monkeypatch.setattr(missing_data, "_MISSING_DATA_CACHE_DIR", cache_dir)
    return index


def test_records_explicit_missing_items(missing_index):
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="fundamentals",
        tool_name="get_fundamentals",
        args={"ticker": "300476", "curr_date": "2026-06-03"},
        content="| ROE | -- | [数据缺失: ROE] |\n| EPS | -- | [数据缺失: 机构一致预期EPS] |",
    )

    assert task is not None
    assert task["ticker"] == "300476"
    assert task["stage_label"] == "基本面"
    assert task["tool_label"] == "综合基本面"
    assert task["missing_items"] == ["ROE", "机构一致预期EPS"]

    tasks = missing_data.get_missing_tasks("300476", "2026-06-03")
    assert [t["id"] for t in tasks] == [task["id"]]


def test_news_title_starting_with_error_is_not_recorded_as_failure(missing_index):
    task = missing_data.record_tool_result(
        ticker="600602",
        trade_date="2026-06-05",
        stage="news",
        tool_name="get_news",
        args={"ticker": "600602"},
        content="Error in the market: regulators announce a new policy",
    )

    assert task is None
    assert missing_data.get_missing_tasks("600602", "2026-06-05") == []


def test_structured_error_prefix_is_recorded_as_failure(missing_index):
    task = missing_data.record_tool_result(
        ticker="600602",
        trade_date="2026-06-05",
        stage="market",
        tool_name="get_indicators",
        args={"ticker": "600602"},
        content="Error: upstream timeout",
    )

    assert task is not None
    assert task["missing_items"] == ["接口返回失败或空数据"]


def test_no_realtime_northbound_data_is_recorded_as_missing(missing_index):
    task = missing_data.record_tool_result(
        ticker="600602",
        trade_date="2026-06-05",
        stage="market",
        tool_name="get_northbound_flow",
        args={"curr_date": "2026-06-05", "include_history": True},
        content="# Northbound Capital Flow\nNo realtime data (non-trading hours or holiday)",
    )

    assert task is not None
    assert task["tool_label"] == "北向资金"
    assert task["missing_items"] == ["接口返回失败或空数据"]


def test_successful_retry_resolves_task(missing_index, monkeypatch):
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args={"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90},
        content="Error retrieving technical summary for 300476: timeout",
    )
    assert task is not None

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "最新收盘价: 12.34\n| 指标 | 数值 |\n|---|---|\n| RSI | 55 |"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    result = missing_data.retry_missing_tasks("300476", "2026-06-03")

    assert result["attempted"] == 1
    assert result["resolved_count"] == 1
    assert result["remaining_count"] == 0
    fake_tool.invoke.assert_called_once_with(task["args"])

    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["status"] == "resolved"
    assert all_tasks[0]["retry_attempts"] == 1


def test_retry_keeps_unresolved_task_when_still_missing(missing_index, monkeypatch):
    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="fundamentals",
        tool_name="get_profit_forecast",
        args={"ticker": "300476"},
        content="[数据缺失: 机构一致预期EPS]",
    )

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "[数据缺失: 机构一致预期EPS]"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_profit_forecast": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    result = missing_data.retry_missing_tasks("300476", "2026-06-03")

    assert result["resolved_count"] == 0
    assert result["remaining_count"] == 1
    assert result["remaining"][0]["status"] == "active"
    assert result["remaining"][0]["retry_attempts"] == 1


def test_snapshot_sync_updates_saved_report(missing_index, tmp_path, monkeypatch):
    log_path = tmp_path / "full_states_log_2026-06-03.json"
    log_path.write_text('{"final_trade_decision": "HOLD"}', encoding="utf-8")
    monkeypatch.setattr(missing_data, "analysis_log_path", lambda ticker, date: Path(log_path))

    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="news",
        tool_name="get_news",
        args={"ticker": "300476", "start_date": "2026-05-27", "end_date": "2026-06-03"},
        content="Error fetching news for 300476: timeout",
    )

    missing_data.sync_missing_snapshot_to_analysis_log("300476", "2026-06-03")

    text = log_path.read_text(encoding="utf-8")
    assert '"missing_data_complete": false' in text
    assert '"tool_name": "get_news"' in text


def test_snapshot_sync_preserves_reanalysis_flag(missing_index, tmp_path, monkeypatch):
    log_path = tmp_path / "full_states_log_2026-06-03.json"
    log_path.write_text(
        '{"missing_data_requires_reanalysis": true}', encoding="utf-8"
    )
    monkeypatch.setattr(
        missing_data, "analysis_log_path", lambda ticker, date: log_path
    )

    missing_data.sync_missing_snapshot_to_analysis_log("300476", "2026-06-03")

    saved = json.loads(log_path.read_text(encoding="utf-8"))
    assert saved["missing_data_requires_reanalysis"] is True


def test_cached_retry_output_is_available_for_reanalysis(missing_index, monkeypatch):
    args = {"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90}
    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error retrieving technical summary for 300476: timeout",
    )

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "补齐后的技术摘要"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("300476", "2026-06-03")

    output = missing_data.cached_retry_output(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
    )

    assert output == "补齐后的技术摘要"
    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["used_in_reanalysis_at"] is not None


def test_consumed_resolved_task_removes_cached_output(missing_index, monkeypatch):
    args = {"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90}
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error retrieving technical summary for 300476: timeout",
    )
    assert task is not None

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "补齐后的技术摘要"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("300476", "2026-06-03")
    resolved = [
        task
        for task in missing_data.get_missing_tasks(
            "300476", "2026-06-03", active_only=False
        )
        if task["status"] == "resolved"
    ]
    cache_path = Path(resolved[0]["resolved_output_path"])
    assert cache_path.exists()

    assert (
        missing_data.cached_retry_output(
            ticker="300476",
            trade_date="2026-06-03",
            stage="market",
            tool_name="get_indicators",
            args=args,
        )
        == "补齐后的技术摘要"
    )
    missing_data.mark_resolved_tasks_consumed("300476", "2026-06-03")

    assert not cache_path.exists()
    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["status"] == "consumed"
    assert (
        missing_data.cached_retry_output(
            ticker="300476",
            trade_date="2026-06-03",
            stage="market",
            tool_name="get_indicators",
            args=args,
        )
        is None
    )


def test_unconsumed_retry_output_survives_unrelated_completed_run(
    missing_index, monkeypatch
):
    args = {"symbol": "300476", "curr_date": "2026-06-03"}
    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error fetching indicators",
    )
    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "补齐后的技术摘要"
    monkeypatch.setattr(
        missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool}
    )
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("300476", "2026-06-03")
    missing_data.mark_resolved_tasks_consumed("300476", "2026-06-03")

    tasks = missing_data.get_missing_tasks(
        "300476", "2026-06-03", active_only=False
    )
    assert tasks[0]["status"] == "resolved"
    assert Path(tasks[0]["resolved_output_path"]).exists()


def test_fresh_run_removes_stale_active_and_consumed_tasks(missing_index):
    args = {"symbol": "300476"}
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error fetching indicators",
    )
    assert task is not None
    task["status"] = "consumed"
    missing_data._save_index([task])

    missing_data.reset_missing_tasks_for_run("300476", "2026-06-03")

    assert missing_data.get_missing_tasks(
        "300476", "2026-06-03", active_only=False
    ) == []


@pytest.mark.parametrize("old_args", [
    {"ticker": "600519"},
    {"ticker": "600519", "curr_date": None},
    {"ticker": "600519", "curr_date": ""},
])
def test_retry_fills_curr_date_for_calls_recorded_before_it_was_required(missing_index, monkeypatch, old_args):
    """v0.5.21 起财报三表的 curr_date 必填；升级前记下的调用没有它（或传了空值），重试时按任务的
    分析日补上，结果仍记到原来那条任务上。"""
    from langchain_core.tools import tool

    seen = []

    @tool
    def get_balance_sheet(ticker: str, curr_date: str, freq: str = "quarterly") -> str:
        """Balance sheet."""
        seen.append((ticker, curr_date, freq))
        return "| 报告日 | 货币资金 |\n|---|---|\n| 2026-03-31 | 111.0 |"

    task = missing_data.record_tool_result(
        ticker="600519",
        trade_date="2026-06-03",
        stage="fundamentals",
        tool_name="get_balance_sheet",
        args=old_args,
        content="Error retrieving balance sheet for 600519: timeout",
    )
    assert task is not None
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_balance_sheet": get_balance_sheet})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    result = missing_data.retry_missing_tasks("600519", "2026-06-03")

    assert seen == [("600519", "2026-06-03", "quarterly")]
    assert result["resolved_count"] == 1
    assert result["remaining_count"] == 0


def test_retry_does_not_add_curr_date_to_tools_that_do_not_require_it(missing_index, monkeypatch):
    from langchain_core.tools import tool

    seen = []

    @tool
    def get_news(ticker: str, curr_date: str = "") -> str:
        """News."""
        seen.append(curr_date)
        return "一条新闻"

    missing_data.record_tool_result(
        ticker="600519",
        trade_date="2026-06-03",
        stage="news",
        tool_name="get_news",
        args={"ticker": "600519"},
        content="Error: upstream timeout",
    )
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_news": get_news})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("600519", "2026-06-03")

    assert seen == [""]
