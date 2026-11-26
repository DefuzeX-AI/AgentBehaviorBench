"""An ACP Agent's steps stand on one timeline, whichever of the three records they come from."""
from datetime import datetime, timedelta, timezone

from agentbench.trajectory.atif.export import build_export
from agentbench.trajectory.atif.slim import stored_document
from tests.atif_fixtures import call, lines, response
from tests.test_atif_acp_otel import (attempt, call_span, exported_span, openclaw_run, reported, spawn_span, tool_span)

# The fixture spans start at this second; ``at`` moves one elsewhere.
START = datetime.fromtimestamp(1_700_000_000, timezone.utc)


def moment(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def at(seconds, row):
    start = 1_700_000_000_000_000_000 + int(seconds * 1_000_000_000)
    row["span"].update(startTimeUnixNano=str(start), endTimeUnixNano=str(start + 500))
    return row


def seconds(step):
    """A step's timestamp as seconds after the fixture start; a span keeps its own text form."""
    return (datetime.fromisoformat(step.timestamp.replace("Z", "+00:00")) - START).total_seconds()


def acp(name, seconds, **data):
    return {"event": name, "timestamp": moment(seconds), "data": {"session_id": "root-session", **data}}


def prompt(seconds):
    return acp("prompt_started", seconds)


def said(seconds, text):
    return acp("session_update", seconds, update={"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})


def tool_report(seconds, call_id, **update):
    kind = "tool_call_update" if "status" in update else "tool_call"
    return acp("session_update", seconds, update={"sessionUpdate": kind, "toolCallId": call_id, **update})


def wire(root, *calls):
    """The interceptor's record: (call id, second, text, emitted tool call ids) per model call."""
    rows = []
    for call_id, seconds, text, emitted in calls:
        rows += [{"event": "llm_request", "timestamp": moment(seconds), "data": {"call_id": call_id, "payload": {"messages": []}}},
                 {"event": "llm_response", "timestamp": moment(seconds + 0.5),
                  "data": {"call_id": call_id, "payload": response(text, [call(cid, "{}") for cid in emitted])}}]
    lines(root / "network.jsonl", rows)


def view(trajectory):
    return [(step.source, step.message, step.extra["abb"].get("sources")) for step in trajectory.steps]


def test_two_text_turns_alternate_and_name_all_three_records(tmp_path):
    # Exported out of order, and neither answer names its turn: only the clocks order them.
    attempt(tmp_path, [at(12, call_span(2, text="second answer")), at(2, call_span(1, text="first answer"))],
            scoped=False, inputs=("one", "two"),
            sessions=([prompt(1), said(3, "first "), said(3.1, "answer"), acp("prompt_completed", 4)],
                      [prompt(11), said(13, "second answer"), acp("prompt_completed", 14)]))
    wire(tmp_path, ("n1", 2.1, "first answer", ()), ("n2", 12.1, "second answer", ()))
    result, _ = build_export(tmp_path)
    document = result.document
    assert view(document) == [("user", "one", ["acp"]), ("agent", "first answer", ["network", "trace", "acp"]),
                              ("user", "two", ["acp"]), ("agent", "second answer", ["network", "trace", "acp"])]
    # A user step stands where its prompt was sent; a model step where its span started.
    assert [seconds(step) for step in document.steps] == [1, 2, 11, 12]
    assert result.validation["status"] == "complete" and result.validation["observed_models"] == 2
    stored = stored_document(document, tmp_path)
    assert stored["steps"][0]["extra"]["abb"] == {
        "input_id": "input-1", "evidence": [{"file": "steps/0001/input.json", "line": None}],
        "execution_started_at": moment(1), "sources": ["acp"]}
    answer = stored["steps"][1]["extra"]["abb"]
    assert answer["sources"] == ["network", "trace", "acp"]
    assert {pointer["file"] for pointer in answer["evidence"]} == {"otel/spans.jsonl", "network.jsonl", "steps/0001/acp-events.jsonl"}


def test_a_turn_the_trace_lost_is_rebuilt_from_the_wire_and_acp(tmp_path):
    attempt(tmp_path, [at(2, call_span(1, text="first answer"))], scoped=False, inputs=("one", "two"),
            sessions=([prompt(1), said(3, "first answer"), acp("prompt_completed", 4)],
                      [prompt(11), tool_report(13, "call-2", title="exec: ls", rawInput={"command": "ls"}),
                       tool_report(14, "call-2", status="completed", rawOutput="a.txt"),
                       said(16, "second answer"), acp("prompt_completed", 17)]))
    wire(tmp_path, ("n1", 2.1, "first answer", ()), ("n2", 12.14, "", ("call-2",)), ("n3", 15.14, "second answer", ()))
    result, _ = build_export(tmp_path)
    document = result.document
    assert view(document) == [("user", "one", ["acp"]), ("agent", "first answer", ["network", "trace", "acp"]),
                              ("user", "two", ["acp"]), ("agent", "", ["network"]),
                              ("agent", "second answer", ["network", "acp"])]
    # The wire request is dated back by the lead the interceptor trails a span by.
    assert [step.timestamp for step in document.steps[3:]] == [moment(12), moment(15)]
    emitted, = document.steps[3].tool_calls
    executed, = document.steps[3].observation.results
    assert emitted.extra == {"abb": {"sources": ["acp"]}} and executed.content == "a.txt"
    assert executed.extra["abb"]["tool_execution"]["tool_name"] == "exec: ls"
    assert not document.extra["abb"]["unassigned_records"] and result.validation["status"] == "complete"
    stored = stored_document(document, tmp_path)
    assert stored["steps"][3]["tool_calls"][0]["extra"] == {"abb": {"sources": ["acp"]}}


def test_a_step_after_the_last_turn_and_text_no_model_call_carries(tmp_path):
    attempt(tmp_path, [at(2, call_span(1, text="answer")), at(30, call_span(2, text="NO_REPLY"))],
            sessions=([prompt(1), said(3, "answer"), acp("prompt_completed", 4), said(20, "[interruption] the gateway went away")],))
    result, _ = build_export(tmp_path)
    assert view(result.document) == [("user", "hello", ["acp"]), ("agent", "answer", ["trace", "acp"]),
                                     ("agent", "[interruption] the gateway went away", ["acp"]),
                                     ("agent", "NO_REPLY", ["trace"])]
    notice = result.document.steps[2]
    assert notice.extra["abb"]["kind"] == "acp_reply" and notice.timestamp == moment(20) and notice.llm_call_count is None


def delegating_run(*, child):
    root_run = openclaw_run(10, 2, under=1, operations=[
        at(2, call_span(11, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read number.txt"})], parent=10)),
        at(3, spawn_span(12, "call-spawn", "run-1", parent=10)), at(4, call_span(13, text="spawned", parent=10))])
    return [exported_span("openclaw.message.processed", 1), *root_run, *openclaw_run(20, 3, under=2, operations=child)]


def test_a_wire_call_runs_where_its_tool_calls_ran_and_is_unknown_otherwise(tmp_path):
    # The trace lost the child's first model call; the tool that call emitted ran in the child's run.
    spans = delegating_run(child=[at(6, tool_span(22, "call-read", "read", {}, "77", parent=20)),
                                  at(7, call_span(23, text="77", parent=20))])
    attempt(tmp_path, spans, sessions=([prompt(1), reported("root-session", "call-spawn"), said(4.5, "spawned"),
                                        acp("prompt_completed", 5)],))
    wire(tmp_path, ("n-child", 5.14, "", ("call-read",)), ("n-stray", 8.14, "a thought nobody else recorded", ()))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    document = result.document
    child, = document.subagent_trajectories
    assert view(child) == [("user", "read number.txt", ["trace", "acp"]), ("agent", "", ["network"]), ("agent", "77", ["trace"])]
    assert seconds(child.steps[0]) == 3 and child.steps[1].tool_calls[0].extra == {"abb": {"sources": ["trace"]}}
    assert view(document) == [("user", "hello", ["acp"]), ("agent", "", ["trace"]), ("agent", "spawned", ["trace", "acp"]),
                              ("agent", "a thought nobody else recorded", ["network"])]
    # No recorded identifier says which execution made the stray call: it is shown, and marked.
    assert [step.extra["abb"].get("owner") for step in document.steps] == [None, None, None, "unknown"]
    assert result.validation["status"] == "partial" and result.validation["unassigned_records"] == 1
    assert "unassigned_record" in [issue["code"] for issue in result.validation["issues"]]
    assert stored_document(document, tmp_path)["steps"][3]["extra"]["abb"]["owner"] == "unknown"


def test_a_background_child_that_outlives_its_turn_stays_in_its_own_trajectory(tmp_path):
    spans = delegating_run(child=[at(12, call_span(23, text="77", parent=20))])
    spans.append(at(13, call_span(31, text="second answer")))
    attempt(tmp_path, spans, scoped=False, inputs=("one", "two"),
            sessions=([prompt(1), reported("root-session", "call-spawn"), said(4.5, "spawned"), acp("prompt_completed", 5)],
                      [prompt(11), said(14, "second answer"), acp("prompt_completed", 15)]))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    document = result.document
    child, = document.subagent_trajectories
    assert [(step.source, step.message) for step in child.steps] == [("user", "read number.txt"), ("agent", "77")]
    # The child answered during the second turn; the root's turns do not show it.
    assert [(step.source, step.message) for step in document.steps] == [
        ("user", "one"), ("agent", ""), ("agent", "spawned"), ("user", "two"), ("agent", "second answer")]
    assert result.validation["status"] == "complete"


def test_without_a_recorded_prompt_start_turns_are_placed_by_identifier(tmp_path):
    # No ACP prompt report: the timeline has no place for the user steps, so the earlier placement stands.
    attempt(tmp_path, [at(2, call_span(1, text="hi there"))])
    wire(tmp_path, ("n1", 2.1, "hi there", ()))
    document = build_export(tmp_path)[0].document
    assert view(document) == [("user", "hello", None), ("agent", "hi there", ["network", "trace"])]
    assert document.steps[1].extra["abb"]["turn_evidence"] == "isolated_single_input_case"
