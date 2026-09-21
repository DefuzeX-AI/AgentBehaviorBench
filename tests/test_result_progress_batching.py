"""Coordinator progress batching keeps bounded latency and complete event order."""

import json
from types import SimpleNamespace

import pytest

from agentbench.cli import result_export
from agentbench.cli.execution import run_benchmark_once
from agentbench.cli.viewer import parse_result_log
from agentbench.harness.result import EvaluationFailure, CaseResult, BenchmarkSuiteResult, SuiteAgentResult


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr(result_export, "time", SimpleNamespace(monotonic=lambda: value[0]))
    return value


def writer_at(tmp_path, **kwargs):
    return result_export.start_result_log(tmp_path / "result.json", suite_id="suite",
                                          selected_agent_ids=("a", "b"), **kwargs)


def records(writer):
    return json.loads(writer.path.read_text())


def test_progress_tick_flushes_within_200ms_even_without_another_event(tmp_path, clock, monkeypatch):
    writer = writer_at(tmp_path, batch_progress=True)
    batches = []
    original = result_export.append_result_events

    def append(path, pending, **kwargs):
        batches.append(list(pending))
        original(path, pending, **kwargs)

    monkeypatch.setattr(result_export, "append_result_events", append)
    for index in range(10):
        writer.append_event({"event": "progress", "status": "started", "sequence": index})
    assert len(records(writer)) == 1
    clock[0] = 0.199
    writer.flush_if_due()
    assert not batches
    clock[0] = 0.2
    writer.flush_if_due()
    assert len(batches) == 1
    assert [event["sequence"] for event in records(writer)[1:]] == list(range(10))
    writer.flush()
    assert len(batches) == 1


@pytest.mark.parametrize("terminal", [
    {"event": "progress", "status": "succeeded"},
    {"event": "progress", "status": "failed"},
    {"event": "step_completed"},
    {"event": "agent_started"},
    {"event": "agent_completed"},
    {"event": "case_completed", "agent_id": "a", "case_index": 0},
    {"event": "suite_failed"},
    {"event": "suite_completed"},
])
def test_lifecycle_and_terminal_events_immediately_flush_pending_rows(tmp_path, clock, terminal):
    writer = writer_at(tmp_path, batch_progress=True)
    writer.append_event({"event": "progress", "status": "started", "sequence": 1})
    writer.append_event({**terminal, "sequence": 2})
    assert [event["sequence"] for event in records(writer)[1:]] == [1, 2]
    clock[0] = 1
    writer.flush_if_due()
    assert len(records(writer)) == 3


def test_batch_size_is_bounded_and_default_writer_is_immediate(tmp_path, clock):
    immediate = writer_at(tmp_path)
    immediate.append_event({"event": "progress", "status": "started"})
    assert len(records(immediate)) == 2
    batched = writer_at(tmp_path, batch_progress=True)
    for index in range(result_export.PROGRESS_BATCH_MAX_EVENTS):
        batched.append_event({"event": "progress", "status": "started", "sequence": index})
    assert len(records(batched)) == result_export.PROGRESS_BATCH_MAX_EVENTS + 1
    assert not batched._buffer.events


def test_failed_flush_retains_pending_events_for_retry(tmp_path, clock, monkeypatch):
    writer = writer_at(tmp_path, batch_progress=True)
    writer.append_event({"event": "progress", "status": "started", "sequence": 1})
    original = result_export.append_result_events
    monkeypatch.setattr(result_export, "append_result_events", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        writer.flush()
    monkeypatch.setattr(result_export, "append_result_events", original)
    writer.flush()
    assert [event["sequence"] for event in records(writer)[1:]] == [1]


def test_redaction_uses_the_suite_environment_snapshot(tmp_path, clock, monkeypatch):
    writer = writer_at(tmp_path, batch_progress=True, environ={"API_TOKEN": "fixture-secret-before"})
    monkeypatch.setenv("API_TOKEN", "fixture-secret-after")
    writer.append_event({"event": "progress", "status": "started", "detail": "fixture-secret-before"})
    writer.flush()
    assert "fixture-secret-before" not in writer.path.read_text()


@pytest.mark.parametrize("selected", [(('a', 4),), (('a', 2), ('b', 3))])
def test_cli_records_effective_case_workers_and_uses_coordinator_tick(tmp_path, clock, selected):
    lines = []

    class Runner:
        concurrency = SimpleNamespace(max_parallel_cases=4)

        def new_suite_id(self):
            return "suite"

        def run(self, agents, *, suite_id, on_event, on_tick, **kwargs):
            on_event({"event": "progress", "status": "started", "agent_id": "a"})
            path = next(tmp_path.glob("result-*.json"))
            assert len(json.loads(path.read_text())) == 1
            clock[0] = 0.2
            on_tick()
            assert len(json.loads(path.read_text())) == 2
            items = tuple(SuiteAgentResult(agent.agent_id, preparation_error=EvaluationFailure("Fixture", "stopped"))
                          for agent in agents)
            return BenchmarkSuiteResult(suite_id, tuple(agent.agent_id for agent in agents), items)

    execution = run_benchmark_once(tuple(SimpleNamespace(agent_id=name, case_count=count) for name, count in selected),
                                   runner=Runner(), output_path=tmp_path / "result.json",
                                   output_fn=lines.append, viewer_starter=None)
    assert any('Case workers: 4 (configured: 4)' in line for line in lines)
    document = parse_result_log(execution.result_log.path)
    assert document["configured_workers"] == 4
    assert document["effective_workers"] == 4
    assert document["total_case_count"] == sum(count for _, count in selected)
    assert document["events"][-1]["event"] == "suite_completed"
