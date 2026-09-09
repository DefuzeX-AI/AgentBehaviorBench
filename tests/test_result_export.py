import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from agentbench.cli.result_export import append_result_event, start_result_log, unique_result_log_path
from agentbench.harness import BenchmarkStepFailure, SuiteAgentResult
from tests.support.results import suite_result

FIXED_TIME = datetime(2026, 8, 19, 1, 1, 1)


def read_events(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_result_log_path_uses_json_and_avoids_collisions(tmp_path) -> None:
    first = unique_result_log_path(tmp_path / "result.json", now=FIXED_TIME)
    first.write_text("", encoding="utf-8")
    second = unique_result_log_path(tmp_path / "result.json", now=FIXED_TIME)

    assert first.name == "result-20260819-010101.json"
    assert second.name == "result-20260819-010101-2.json"


def test_result_log_appends_trace_events_without_losing_earlier_data(
    tmp_path,
) -> None:
    result = suite_result("agent-a")
    benchmark = result.items[0].benchmark
    assert benchmark is not None
    step = benchmark.steps[0]
    writer = start_result_log(
        tmp_path / "result.json",
        suite_id="suite_test",
        selected_agent_ids=("agent-a",),
        now=FIXED_TIME,
    )

    writer.append_step_started("agent-a", step.input_id, step.payload)
    writer.append_step_completed("agent-a", step)
    writer.append_step_failed(
        "agent-a",
        BenchmarkStepFailure(
            input_id="input-b",
            payload={"prompt": "kept before failure"},
            output={"answer": "partial"},
            raw_output={"node": "tool"},
            error_type="RuntimeError",
            error_message="judge unavailable",
        ),
    )
    writer.append_agent_complete(
        SuiteAgentResult(
            agent_id="agent-a",
            benchmarks=(benchmark, benchmark),
            requested_case_count=2,
        )
    )
    writer.append_suite_complete(result)

    events = read_events(writer.path)

    assert [event["event"] for event in events] == [
        "run_started",
        "step_started",
        "step_completed",
        "step_failed",
        "agent_completed",
        "suite_completed",
    ]
    assert {event["suite_id"] for event in events} == {"suite_test"}
    assert events[1]["payload"] == {"prompt": "Prompt for agent-a"}
    assert events[2]["step"]["raw_output"] == {
        "node": "final",
        "messages": ["trace for agent-a"],
    }
    assert events[3]["failure"]["payload"] == {"prompt": "kept before failure"}
    assert events[4]["item"]["requested_case_count"] == 2
    assert events[4]["item"]["completed_case_count"] == 2
    assert len(events[4]["item"]["benchmarks"]) == 2
    assert events[-1]["summary"]["suite_passed"] is True


def test_result_log_records_suite_failure(tmp_path) -> None:
    writer = start_result_log(
        tmp_path / "result.json",
        suite_id="suite_failed",
        selected_agent_ids=("agent-a",),
        now=FIXED_TIME,
    )

    writer.append_suite_error(RuntimeError("service unavailable"))

    assert read_events(writer.path)[-1] == {
        "event": "suite_failed",
        "suite_id": "suite_failed",
        "error": {
            "type": "RuntimeError",
            "message": "service unavailable",
        },
    }


def test_failed_snapshot_replace_preserves_previous_document(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    append_result_event(path, {"event": "first"})
    original = path.read_bytes()

    def fail_replace(*args):
        raise OSError("interrupted before replacement")

    monkeypatch.setattr("agentbench.cli.result_export.os.replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        append_result_event(path, {"event": "second"})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_snapshot_updates_keep_all_events(tmp_path):
    path = tmp_path / "result.json"
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda i: append_result_event(path, {"index": i}), range(20)))
    assert {event["index"] for event in read_events(path)} == set(range(20))
