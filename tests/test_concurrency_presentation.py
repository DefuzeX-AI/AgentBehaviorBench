"""Concurrency boundaries for event persistence and read-only presentation."""

import json
from types import SimpleNamespace

import pytest

from agentbench.adapter import AdapterInvocation
from agentbench.cli.execution import run_benchmark_once
from agentbench.cli.result_export import start_result_log
from agentbench.cli.terminal_ui.llm_activity import LLMActivity
from agentbench.cli.terminal_ui.progress import ProgressPrinter
from agentbench.cli.terminal_ui.presentation import format_case_event, print_agent_complete
from agentbench.cli.viewer import parse_result_log
from agentbench.harness.progress import BenchmarkProgress
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.result import EvaluationFailure, CaseResult, BenchmarkStepResult, BenchmarkSuiteResult, SuiteAgentResult
from agentbench.observe.view_api import SuiteRunCatalogAPI
from agentbench.runtime.interception import TraceEvent


def failed(agent):
    return SuiteAgentResult(agent, preparation_error=EvaluationFailure("FixtureError", "failed"))


def test_coordinator_events_preserve_shapes_and_group_repeated_inputs(tmp_path):
    writer = start_result_log(tmp_path / "result.json", suite_id="suite", selected_agent_ids=("a", "b"))
    step = BenchmarkStepResult("input-1", {"question": "hello"}, AdapterInvocation("answer", {"raw": True}))
    for agent, case in (("b", 1), ("a", 1), ("b", 2), ("a", 2)):
        writer.append_event({"event": "step_completed", "agent_id": agent,
                             "job_id": f"job-{agent}", "case_index": case,
                             "case_id": f"case-{case}", "artifact_run_id": f"run-{agent}-{case}",
                             "step": step})
    for agent in ("b", "a"):
        writer.append_event({"event": "agent_completed", "agent_id": agent, "item": failed(agent)})
    result = parse_result_log(writer.path)
    assert [item["agent_id"] for item in result["agents"]] == ["a", "b"]
    assert [job["agent_id"] for job in result["jobs"]] == ["a", "b"]
    assert all(job["status"] == "failed" for job in result["jobs"])
    for item in result["agents"]:
        assert [group["case_index"] for group in item["case_step_events"]] == [1, 2]
        assert item["step_events"][0]["step"] == {"input_id": "input-1", "payload": {"question": "hello"},
                                                  "output": "answer", "raw_output": {"raw": True}}
    assert isinstance(json.loads(writer.path.read_text()), list)
    with pytest.raises(ValueError, match="suite ID"):
        writer.append_event({"event": "progress", "suite_id": "another-suite"})


def test_catalog_jobs_do_not_create_fake_runs_and_only_expose_selected_artifacts(tmp_path):
    writer = start_result_log(tmp_path / "result.json", suite_id="suite", selected_agent_ids=("a", "b"))
    writer.append_event({"event": "agent_queued", "agent_id": "b", "job_id": "job-b"})
    writer.append_event({"event": "agent_started", "agent_id": "a", "job_id": "job-a"})
    catalog = SuiteRunCatalogAPI(writer.path)
    pending = catalog.route("/api/observe/runs", {})
    assert pending["runs"] == [] and pending["default_run"] is None
    assert [(job["agent_id"], job["status"]) for job in pending["jobs"]] == [("a", "running"), ("b", "queued")]
    directory = tmp_path / "run-a"
    directory.mkdir()
    (directory / "run.json").write_text(json.dumps({"schema": "abb.evaluate.run.v1", "run_id": "run-a",
                                                   "agent_id": "a", "status": "running"}))
    writer.append_event({"event": "progress", "agent_id": "a", "job_id": "job-a", "case_index": 2,
                         "case_id": "case-2", "artifact_run_id": "run-a", "artifact_directory": str(directory)})
    # An unselected Agent cannot register a directory, even if the path exists.
    writer.append_event({"event": "progress", "agent_id": "outsider", "artifact_directory": str(directory)})
    live = catalog.route("/api/observe/runs", {})
    assert len(live["runs"]) == 1
    assert live["runs"][0]["case_index"] == 2
    assert live["runs"][0]["job_id"] == "job-a"
    assert catalog.route("/api/observe/runs/run-a/metadata", {})["agent_id"] == "a"
    with pytest.raises(ValueError, match="not registered"):
        catalog.route("/api/observe/runs/job-b/metadata", {})
    writer.append_suite_error(RuntimeError("interrupted"))
    assert all(job["status"] == "cancelled" for job in catalog.route("/api/observe/runs", {})["jobs"])


def test_stored_log_without_case_metadata_remains_readable(tmp_path):
    writer = start_result_log(tmp_path / "result.json", suite_id="old", selected_agent_ids=("a",))
    writer.append_event({"event": "step_started", "agent_id": "a", "input_id": "input-1", "payload": "hello"})
    writer.append_agent_complete(failed("a"))
    result = parse_result_log(writer.path)
    assert result["agents"][0]["case_step_events"][0]["case_id"] is None
    assert result["jobs"][0]["job_id"] is None
    assert result["jobs"][0]["status"] == "failed"


def test_concurrent_terminal_events_are_self_identifying_and_never_animate():
    lines = []
    activity = LLMActivity(lines.append, live_updates=True)
    activity.set_concurrent(True)
    progress = ProgressPrinter(lines.append, llm_activity=activity, concurrent=True, live_updates=True)
    for agent in ("a", "b"):
        progress(SimpleNamespace(agent_id=agent, stage="case_generation", status="started", detail=None,
                                 job_id=f"job-{agent}", case_index=0, artifact_run_id=f"run-{agent}"))
        activity.emit(TraceEvent("llm_request", {"agent_id": agent, "job_id": f"job-{agent}",
                                                 "artifact_run_id": f"run-{agent}", "call_id": "same-call",
                                                 "payload": {"prompt": agent}}))
    for agent in ("b", "a"):
        activity.emit(TraceEvent("llm_response", {"agent_id": agent, "job_id": f"job-{agent}",
                                                  "case_index": 0,
                                                  "call_id": "same-call", "payload": {"output": f"reply-{agent}"}}))
    assert len(lines) == 6
    assert lines[0] == "[a · case 1] Case generation · started"
    assert "[b · case 1] Model ←" in lines[4] and "reply-b" in lines[4]
    assert "[a · case 1] Model ←" in lines[5] and "reply-a" in lines[5]
    assert activity._animation_thread is None and progress._animation_thread is None
    progress.close()


@pytest.mark.parametrize('concurrent', [False, True])
def test_evaluation_http_polls_are_compact_and_failures_remain_visible(concurrent):
    lines = []
    activity = LLMActivity(lines.append, live_updates=False)
    activity.set_concurrent(concurrent)
    base = {'agent_id': 'react-agent', 'job_id': 'case-job', 'case_index': 0,
            'artifact_run_id': 'run-one', 'purpose': 'evaluation', 'method': 'GET',
            'host': 'defuzex.ai', 'path': '/api/agentdefuze/sdk/v2/operations/operation-id/'}
    for index in range(25):
        data = {**base, 'call_id': f'call-{index}'}
        activity.emit(TraceEvent('tool_request', data))
        activity.emit(TraceEvent('tool_response', {**data, 'status': 200}))
    assert len(lines) == 3
    assert 'polling started' in lines[0]
    assert '10 status checks' in lines[1]
    assert '25 status checks' in lines[2]
    assert all('operation-id' not in line and 'call-' not in line for line in lines)

    activity.emit(TraceEvent('tool_error', {**base, 'call_id': 'failed-call',
                                           'error': 'connection timed out'}))
    assert len(lines) == 4
    assert 'connection timed out' in lines[-1]
    assert 'failed-call' in lines[-1]

    activity.emit(TraceEvent('tool_response', {**base, 'call_id': 'bad-status', 'status': 503}))
    assert 'HTTP 503' in lines[-1] and 'bad-status' in lines[-1]


def test_nonpolling_evaluation_http_prints_one_result_line():
    lines = []
    activity = LLMActivity(lines.append, live_updates=False)
    activity.set_concurrent(True)
    data = {'agent_id': 'react-agent', 'case_index': 1, 'purpose': 'evaluation',
            'method': 'POST', 'host': 'defuzex.ai', 'path': '/api/agentdefuze/sdk/v2/runs/',
            'call_id': 'request-id'}
    activity.emit(TraceEvent('tool_request', data))
    activity.emit(TraceEvent('tool_response', {**data, 'status': 201}))
    assert lines == ['[react-agent · case 2] SDK API · POST defuzex.ai/api/agentdefuze/sdk/v2/runs/ → HTTP 201']


def test_poll_summaries_keep_parallel_cases_separate():
    lines = []
    activity = LLMActivity(lines.append, live_updates=False)
    activity.set_concurrent(True)
    for case in (0, 1):
        data = {'agent_id': 'react-agent', 'job_id': f'job-{case}', 'case_index': case,
                'artifact_run_id': f'run-{case}', 'purpose': 'evaluation', 'method': 'GET',
                'host': 'defuzex.ai', 'path': '/api/operations/same-path/'}
        for index in range(10):
            activity.emit(TraceEvent('tool_request', {**data, 'call_id': f'{case}-{index}'}))
            activity.emit(TraceEvent('tool_response', {**data, 'call_id': f'{case}-{index}', 'status': 200}))
    assert len(lines) == 4
    assert lines[0].startswith('[react-agent · case 1]')
    assert lines[1].startswith('[react-agent · case 1]') and '10 status checks' in lines[1]
    assert lines[2].startswith('[react-agent · case 2]')
    assert lines[3].startswith('[react-agent · case 2]') and '10 status checks' in lines[3]


def test_case_lifecycle_line_keeps_verdict_without_long_job_id():
    event = {'event': 'case_completed', 'agent_id': 'react-agent', 'case_index': 2,
             'job_id': 'case_0123456789abcdef', 'status': 'completed',
             'case_result': SimpleNamespace(execution_status='completed', judge_status='issue')}
    assert format_case_event(event) == '[react-agent · case 3] Finished · completed · Judge issue'


def test_cli_persists_standard_events_once_and_uses_callbacks_only_for_display(tmp_path):
    agent = SimpleNamespace(agent_id="a", case_count=1)
    item = failed("a")
    progress_event = BenchmarkProgress(stage="case_generation", status="started", agent_id="a")

    class EventRunner:
        concurrency = ConcurrencySettings()

        def new_suite_id(self):
            return "suite"

        def run(self, agents, *, suite_id, on_agent_start, on_agent_complete, on_progress,
                on_event, on_tick):
            on_agent_start(agent, 1, 1)
            on_event({"event": "progress", "agent_id": "a", "stage": "case_generation", "status": "started"})
            on_progress(progress_event)
            on_event({"event": "step_started", "agent_id": "a", "job_id": "job-a", "input_id": "input-1", "payload": "hello"})
            on_event({"event": "agent_completed", "agent_id": "a", "job_id": "job-a", "item": item})
            on_agent_complete(item)
            on_tick()
            return BenchmarkSuiteResult(suite_id, ("a",), (item,))

    execution = run_benchmark_once((agent,), runner=EventRunner(),
                                   output_path=tmp_path / "result.json", output_fn=lambda line: None,
                                   viewer_starter=None)
    events = json.loads(execution.result_log.path.read_text())
    for kind in ("progress", "step_started", "agent_completed", "suite_completed"):
        assert sum(event["event"] == kind for event in events) == 1
    assert next(event for event in events if event["event"] == "step_started")["job_id"] == "job-a"


def test_same_agent_cases_keep_independent_state_and_partial_recovery(tmp_path):
    writer = start_result_log(tmp_path / "result.json", suite_id="suite", selected_agent_ids=("a",),
                               configured_workers=4, selected_case_counts={"a": 4})
    writer.append_event({"event": "agent_started", "agent_id": "a", "job_id": "parent-a"})
    for index in range(4):
        writer.append_event({"event": "case_started", "agent_id": "a", "agent_job_id": "parent-a",
                             "job_id": f"case-{index}", "case_index": index, "case_id": f"id-{index}"})
    live = parse_result_log(writer.path)
    assert live["effective_workers"] == 4 and live["total_case_count"] == 4
    assert live["jobs"][0]["counts"]["running"] == 4
    assert [case["job_id"] for case in live["jobs"][0]["cases"]] == [f"case-{index}" for index in range(4)]
    cases = tuple(CaseResult("a", index, f"case-{index}", "failed" if index == 2 else "cancelled",
                             case_id=f"id-{index}", error_type="Fixture" if index == 2 else "RunCancelled",
                             error_message="stopped") for index in range(4))
    writer.append_event({"event": "case_completed", "agent_id": "a", "agent_job_id": "parent-a",
                         "job_id": "case-2", "case_index": 2, "case_result": cases[2]})
    live = parse_result_log(writer.path)
    assert live["jobs"][0]["status"] == "running"
    assert live["jobs"][0]["counts"]["running"] == 3 and live["jobs"][0]["counts"]["failed"] == 1
    assert live["agents"][0]["case_results"][0]["case_index"] == 2
    writer.append_partial_results((SuiteAgentResult("a", case_results=cases, requested_case_count=4),))
    final = parse_result_log(writer.path)
    assert len([event for event in final["events"] if event["event"] == "case_completed"]) == 4
    assert [case["case_index"] for case in final["agents"][0]["case_results"]] == [0, 1, 2, 3]
    assert final["jobs"][0]["counts"]["cancelled"] == 3
    assert "benchmark" not in final["agents"][0]


@pytest.mark.parametrize("status", ["cancelled", "skipped"])
def test_terminal_agent_aggregate_preserves_nonfailure_case_status(status):
    item = SuiteAgentResult("a", case_results=(CaseResult("a", 0, "case-0", status),))
    lines = []
    print_agent_complete(item, lines.append)
    assert status.upper() in lines[0]
    assert "FAILED" not in lines[0]
