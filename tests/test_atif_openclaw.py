"""OpenClaw native spawn receipts across the ABB reader, resolver and ATIF export."""
import pytest

from agentbench.trajectory.atif.adapters import ADAPTER_NAMES
from agentbench.trajectory.atif.export import build_export
from tests.atif_fixtures import event, fixture, lines, save, span


def spawn(call, run, child="[REDACTED]", parent="root-session", task="read test.txt", **changes):
    args = {"task": task} if task else {}
    receipt = {"status": "accepted", "runId": run, "childSessionKey": child}
    return operation(call, parent, changes.pop("name", "sessions_spawn: task"),
                     args, {"details": {**receipt, **changes}}, error=False)


def operation(call, session, name, args, output, *, error=False):
    rows = [span(call, "root", "tool", name, input=args, tool_call_id=call),
            event("span_error", span_id=call, error=output) if error else event("span_end", span_id=call, output=output)]
    native = event("session_update", session_id=session, update={"toolCallId": call, "rawOutput": output})
    return rows, native


def export(tmp_path, *operations):
    folder = fixture(tmp_path)
    save(folder / "acp-summary.json", {"session": {"sessionId": "root-session"}})
    rows = [span("root")]
    for framework, _ in operations:
        rows.extend(framework)
    lines(folder / "framework.jsonl", rows)
    lines(folder / "acp-events.jsonl", [native for _, native in operations])
    exported, _ = build_export(tmp_path, adapters=ADAPTER_NAMES)
    return exported


def observations(doc):
    return {result.extra["abb"]["tool_execution"]["tool_call_id"]: result
            for step in doc.steps if step.observation for result in step.observation.results}


def test_distinct_accepted_children_with_same_task_survive_failed_wait(tmp_path):
    out = export(tmp_path, spawn("call-1", "run-1"), spawn("call-2", "run-2"),
                 operation("wait", "root-session", "agents_wait", {}, {"status": "not_found"}, error=True))
    doc = out.document
    children = {child.trajectory_id: child for child in doc.subagent_trajectories}
    results = observations(doc)
    assert len(children) == 2 and not results["wait"].subagent_trajectory_ref
    for i in (1, 2):
        ref, = results[f"call-{i}"].subagent_trajectory_ref
        child = children[ref.trajectory_id]
        assert child.extra["abb"]["execution"]["key"]["native_id"] == f"run-{i}"
        assert child.extra["abb"]["execution"]["key"]["native_session_id"] is None
        assert child.extra["abb"]["execution"]["status"] == "accepted"
        assert [(s.source, s.message) for s in child.steps] == [("user", "read test.txt")]
    assert len(out.association["delegation_facts"]) == 2


def test_owned_native_read_and_nested_delegation(tmp_path):
    out = export(tmp_path, spawn("first", "run-1", "session-a"),
                 spawn("nested", "run-2", "session-b", parent="session-a"),
                 operation("read", "session-b", "read", {"path": "test.txt"}, "77"))
    root = out.document
    first, = root.subagent_trajectories
    nested, = first.subagent_trajectories
    assert observations(root)["first"].subagent_trajectory_ref[0].trajectory_id == first.trajectory_id
    assert observations(first)["nested"].subagent_trajectory_ref[0].trajectory_id == nested.trajectory_id
    assert observations(nested)["read"].content == "77"
    assert out.validation["unassigned_records"] == 0


def test_reused_session_never_guesses_owner_of_read(tmp_path):
    out = export(tmp_path, spawn("one", "run-1", "shared"), spawn("two", "run-2", "shared"),
                 operation("read", "shared", "read", {}, "77"))
    assert out.validation["embedded_children"] == 2
    assert out.validation["unassigned_records"] == 1
    assert all(not observations(child) for child in out.document.subagent_trajectories)


def test_conflicting_and_unrooted_siblings_leave_good_spawn_intact(tmp_path):
    out = export(tmp_path, spawn("one", "duplicate"), spawn("two", "duplicate"),
                 spawn("self", "run-3", "root-session"), spawn("orphan", "run-4", parent="unknown"),
                 spawn("valid", "run-5"))
    valid, = out.document.subagent_trajectories
    assert observations(out.document)["valid"].subagent_trajectory_ref[0].trajectory_id == valid.trajectory_id
    assert {"invalid_delegation", "openclaw_ambiguous_spawn", "openclaw_self_delegation"} <= {
        i["code"] for i in out.validation["issues"]}


def test_bare_receipt_can_record_a_fact_without_a_child_step(tmp_path):
    out = export(tmp_path, spawn("one", "run-1", task=None))
    assert out.validation["embedded_children"] == 0
    fact, = out.association["delegation_facts"]
    assert fact["child_run_id"] == "run-1" and fact["status"] == "accepted"


@pytest.mark.parametrize("tool", [
    spawn("one", "run-1", status="rejected"), spawn("one", "run-1", name="not_sessions_spawn"),
    spawn("one", " [REDACTED] "), spawn("one", None), spawn("one", "run-1", child=None),
    operation("one", "root-session", "sessions_spawn", {}, {"content": "accepted run-1"}),
    operation("one", "root-session", "sessions_spawn", {}, {"isError": True, "details": {
              "status": "accepted", "runId": "run-1", "childSessionKey": "child"}}),
    operation("one", "root-session", "sessions_spawn", {}, {"details": {"status": "accepted",
              "runId": "run-1", "childSessionKey": "child"}}, error=True),
])
def test_no_delegation_from_unconfirmed_receipts(tmp_path, tool):
    out = export(tmp_path, tool)
    assert not out.association["delegation_facts"] and not out.document.subagent_trajectories


def test_native_child_read_and_gateway_notice_have_separate_provenance(tmp_path):
    from agentbench.trajectory.atif.reader import read_evidence
    from agentbench.trajectory.atif.hierarchy import resolve_hierarchy
    from tests.atif_fixtures import response
    folder = fixture(tmp_path)
    rows, notification = spawn("spawn", "run-1", child="child-session")
    lines(folder / "framework.jsonl", [span("root"), *rows])
    save(folder / "acp-summary.json", {"session": {"sessionId": "root-session"}})
    lines(folder / "acp-events.jsonl", [notification])
    lines(tmp_path / "network.jsonl", [event("llm_request", call_id="parent-answer",
          payload={"messages": [{"role": "user", "content": "Completion: read 77"}]}),
          event("llm_response", call_id="parent-answer", payload=response("77"))])
    attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "read",
             "gen_ai.conversation.id": "child-session", "gen_ai.tool.call.id": "child-read",
             "gen_ai.tool.call.result": "77"}
    native = {"schema": "abb.agent-otel.v1", "origin": "agent_native", "resource": {},
              "scope": {"name": "openclaw"}, "span": {"traceId": "aa" * 16, "spanId": "bb" * 8,
              "name": "openclaw.tool.execution", "startTimeUnixNano": "1234567890123456789",
              "endTimeUnixNano": "1234567890123456799",
              "attributes": [{"key": k, "value": {"stringValue": v}} for k, v in attrs.items()]}}
    lines(tmp_path / "otel/spans.jsonl", [native])
    bundle = read_evidence(tmp_path)
    graph = resolve_hierarchy(bundle, adapters=["openclaw"])
    read = next(t for t in bundle.tools if t["tool_call_id"] == "child-read")
    assert read["outputs"] == "77" and graph.owners[read["id"]] != graph.root_id
    assert graph.owners[read["id"]] is not None
    assert {r["file"] for r in read["evidence"]} == {"otel/spans.jsonl"}
    parent = next(m for m in bundle.models if m.get("call_id") == "parent-answer")
    assert {r["file"] for r in parent["evidence"]} == {"network.jsonl"}
    assert [f["status"] for f in graph.delegation_facts] == ["accepted"]
    assert all(row.get("event") != "message_delivered" for row in bundle.native_events)
