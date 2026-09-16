"""Reporting and cleanup failures must not destroy completed Agent outcomes."""

import json
from types import MappingProxyType, SimpleNamespace

import pytest

from agentbench.cli import result_export
from agentbench.cli.execution import run_benchmark_once
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.result import EvaluationFailure, CaseResult, SuiteAgentResult
from agentbench.observe.view_api import suite_jobs


class Runner:
    concurrency = ConcurrencySettings()

    def new_suite_id(self):
        return "suite"


def run(tmp_path, runner, *, lines=None, viewer=None, output=None):
    return run_benchmark_once((SimpleNamespace(agent_id="a", case_count=1), SimpleNamespace(agent_id="b", case_count=1)),
                              runner=runner, output_path=tmp_path / "result.json",
                              output_fn=output or (lines if lines is not None else []).append,
                              viewer_starter=None if viewer is None else lambda path: viewer)


def test_original_failure_survives_log_flush_and_viewer_cleanup_errors(tmp_path, monkeypatch):
    original = RuntimeError("original worker failure")
    stops = []

    def broken_flush(self):
        raise OSError("disk full")

    def broken_stop():
        stops.append(True)
        raise OSError("viewer stop failed")

    class BrokenRunner(Runner):
        def run(self, agents, **kwargs):
            monkeypatch.setattr(result_export.ResultLogWriter, "flush", broken_flush)
            raise original

    lines = []
    with pytest.raises(RuntimeError) as caught:
        run(tmp_path, BrokenRunner(), lines=lines,
            viewer=SimpleNamespace(url="http://127.0.0.1/", stop=broken_stop))
    assert caught.value is original
    assert stops == [True]
    assert any("Flush result log failed" in line for line in lines)
    assert any("Stop viewer failed" in line for line in lines)


def test_interrupt_recovers_unreported_outcomes_without_duplicating_saved_agents(tmp_path):
    first = SuiteAgentResult("a", preparation_error=EvaluationFailure("Fixture", "failed"))
    second = SuiteAgentResult("b", preparation_error=EvaluationFailure("RunCancelled", "cancelled"))
    stops = []

    class InterruptedRunner(Runner):

        def run(self, agents, *, on_event, **kwargs):
            on_event({"event": "agent_completed", "agent_id": "a", "job_id": "job-a", "item": first})
            exc = KeyboardInterrupt()
            exc.partial_items = (first, second)
            raise exc

    execution = run(tmp_path, InterruptedRunner(),
                    viewer=SimpleNamespace(url="http://127.0.0.1/", stop=lambda: stops.append(True)))
    events = json.loads(execution.result_log.path.read_text())
    assert [event["agent_id"] for event in events if event["event"] == "agent_completed"] == ["a", "b"]
    assert events[-1]["event"] == "suite_failed"
    assert execution.exit_code == 130 and execution.viewer is None
    assert stops == [True]
    assert [job["status"] for job in suite_jobs(events)] == ["failed", "cancelled"]


def test_interrupt_with_unsavable_log_keeps_exit_130_and_reports_missing_save(tmp_path, monkeypatch):
    class InterruptedRunner(Runner):
        def run(self, agents, **kwargs):
            def fail(self):
                raise OSError("disk full")
            monkeypatch.setattr(result_export.ResultLogWriter, "flush", fail)
            raise KeyboardInterrupt()

    lines = []
    execution = run(tmp_path, InterruptedRunner(), lines=lines)
    assert execution.exit_code == 130
    assert "Benchmark interrupted; some results could not be saved." in lines
    assert "Benchmark interrupted; results retained." not in lines


def test_standard_event_is_saved_before_its_display_callback_fails(tmp_path):
    item = SuiteAgentResult("a", preparation_error=EvaluationFailure("Fixture", "failed"))
    original = BrokenPipeError("closed terminal")

    class EventRunner(Runner):
        def run(self, agents, *, on_event, on_agent_complete, **kwargs):
            on_event({"event": "agent_completed", "agent_id": "a", "item": item})
            on_agent_complete(item)

    def output(line):
        if line.startswith("Result:"):
            raise original

    with pytest.raises(BrokenPipeError) as caught:
        run(tmp_path, EventRunner(), output=output)
    assert caught.value is original
    events = json.loads(next(tmp_path.glob("result-*.json")).read_text())
    assert [event["agent_id"] for event in events if event["event"] == "agent_completed"] == ["a"]


def test_failure_during_viewer_startup_output_still_stops_started_viewer(tmp_path):
    stops = []
    original = BrokenPipeError("startup output unavailable")

    def output(line):
        raise original

    with pytest.raises(BrokenPipeError) as caught:
        run(tmp_path, Runner(), output=output,
            viewer=SimpleNamespace(url="http://127.0.0.1/", stop=lambda: stops.append(True)))
    assert caught.value is original and stops == [True]


def test_result_redaction_uses_existing_runner_factory_snapshot(tmp_path, monkeypatch):
    class SnapshotRunner(Runner):
        _runner_factory = SimpleNamespace(environ=MappingProxyType({"API_KEY": "fixture-old-secret"}))

        def run(self, agents, *, on_event, **kwargs):
            on_event({"event": "step_started", "payload": "fixture-old-secret"})
            raise RuntimeError("fixture failure")

    monkeypatch.setenv("API_KEY", "fixture-new-secret")
    with pytest.raises(RuntimeError, match="fixture failure"):
        run(tmp_path, SnapshotRunner())
    assert "fixture-old-secret" not in next(tmp_path.glob("result-*.json")).read_text()


def test_job_display_keeps_concurrent_cases_separate_from_generation():
    events = [
        {"event": "run_started", "selected_agent_ids": ["a"], "selected_case_counts": {"a": 2}},
        {"event": "progress", "agent_id": "a", "agent_job_id": "parent-a", "job_id": "case-job-0",
         "phase": "execute", "case_index": 0, "case_id": "first-case", "artifact_run_id": "first-run"},
        {"event": "progress", "agent_id": "a", "agent_job_id": "parent-a", "job_id": "case-job-1",
         "phase": "execute", "case_index": 1, "case_id": "second-case", "artifact_run_id": "second-run"},
    ]
    job = suite_jobs(events)[0]
    assert job["counts"]["running"] == 2
    assert [case["artifact_run_id"] for case in job["cases"]] == ["first-run", "second-run"]
    assert job["job_id"] == "parent-a"
    assert "case_index" not in job and "artifact_run_id" not in job
    events.append({"event": "progress", "agent_id": "a", "job_id": "parent-a", "phase": "generate", "status": "started"})
    job = suite_jobs(events)[0]
    assert job["generation_status"] == "running"
    assert [case["case_id"] for case in job["cases"]] == ["first-case", "second-case"]
