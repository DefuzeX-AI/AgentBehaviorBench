from tests.atif_fixtures import event, lines, save
from agentbench.trajectory.atif.export import build_export


def turn(root, invocation):
    folder = root / ("invocation-" + invocation)
    save(folder / "input/request.json", {"schema": "abb.invocation.v1", "run_id": invocation,
        "session_id": "run", "input": invocation, "timestamp": "2001-01-01T00:00:00Z"})
    save(folder / "output/result.json", {"run_id": invocation, "status": "succeeded", "output": "Done"})
    return folder / "output"


def clock(invocation, when, sid, framework=None):
    return {"event": "span", "source": "otel", "run_id": "run", "data": {
        "trace_id": "trace", "span_id": sid, "name": "abb.execute" if not framework else "edit",
        "attributes": {"abb.invocation_id": invocation, **({"abb.framework_span_id": framework} if framework else {})},
        "start_time": when}}


def test_shared_spans_follow_their_turn_and_only_otel_supplies_times(tmp_path):
    save(tmp_path / "run.json", {"run_id": "run", "status": "stopped"})
    start = ["2026-01-01T12:00:00Z", "2026-01-01T12:01:00Z"]
    shared_rows = []
    for index, key in enumerate(("z", "a")):
        folder = turn(tmp_path, key)
        boundary = clock(key, start[index], key)
        lines(folder / "otel-live.jsonl", [boundary, boundary])
        rows = [boundary]
        if index:
            rows.append(clock(key, "2026-01-01T12:01:01Z", "operation", "span"))
        lines(folder / "otel.jsonl", rows)
        identity = {"span_id": "span", "tool_call_id": "reused", "invocation_id": key}
        shared_rows.extend([event("span_start", kind="tool", name="any-edit", input={"path": key}, **identity),
                            event("span_end", output=key, **identity)])
    lines(tmp_path / "session/output/framework.jsonl", shared_rows)
    result, bundle = build_export(tmp_path)
    steps = result.document.steps
    assert len(bundle.inputs) == len(bundle.tools) == 2
    assert [s.message for s in steps] == ["z", "", "Done", "a", "", "Done"]
    assert [s.timestamp for s in steps] == [None, None, None, None, "2026-01-01T12:01:01Z", None]
    assert [s.extra["abb"]["execution_start"]["start_time"] for s in steps if s.source == "user"] == start
    assert [s.observation.results[0].content for s in steps if s.observation] == ["z", "a"]


def test_missing_or_ambiguous_otel_identity_never_uses_request_time(tmp_path):
    save(tmp_path / "run.json", {"run_id": "run", "status": "stopped"})
    folder = turn(tmp_path, "a")
    turn(tmp_path, "b")
    one, two = [clock("a", "2026-01-01T12:00:00Z", sid) for sid in ("one", "two")]
    lines(folder / "otel.jsonl", [one, two])
    result, _ = build_export(tmp_path)
    assert [s.message for s in result.document.steps] == ["a", "Done", "b", "Done"]
    assert all(not s.timestamp and "execution_start" not in s.extra["abb"] for s in result.document.steps)
    assert {"turn_order_uncertain", "ambiguous_otel_clock"} <= {i["code"] for i in result.document.extra["abb"]["issues"]}
