"""One operation recorded by the trace, the wire and ACP becomes one record that names its sources."""
from datetime import datetime, timedelta, timezone

from agentbench.trajectory.atif.sources.merge import (
    ACP, NETWORK, NETWORK_LEAD, TRACE, acp_tool, acp_tool_reports, clock, merge, output_key, pair_models)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def moment(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def traced(name, seconds, *, text="", calls=()):
    """A model record read from an exported span."""
    when = clock(moment(seconds))
    return {"id": name, "kind": "model", "source": "agent_native", "call_id": None,
            "output": {"text": text, "tool_calls": [{"id": cid, "name": "read", "arguments": args} for cid, args in calls]},
            "evidence": [{"file": "otel/spans.jsonl", "line": int(seconds * 10) + 1}],
            "agent_otel": [{"start_time": when["start_time"], "unix_nano": str(when["unix_nano"])}]}


def wired(name, seconds, *, text="", calls=()):
    """A model record read from the interceptor's wire record."""
    return {"id": name, "kind": "model", "source": "wire", "call_id": "wire-" + name,
            "output": {"text": text, "tool_calls": [{"id": cid, "name": "read", "arguments": args} for cid, args in calls]},
            "client_output": None, "evidence": [{"file": "logs/network.jsonl", "line": int(seconds * 10) + 1}],
            "sources": [NETWORK], "clock": clock(moment(seconds), NETWORK_LEAD)}


def tool(name, call_id):
    return {"id": name, "kind": "tool", "source": "agent_native", "tool_call_id": call_id,
            "evidence": [{"file": "otel/spans.jsonl", "line": 90}]}


def report(seconds, line, *, session="root-session", **update):
    return {"event": "session_update", "timestamp": moment(seconds),
            "data": {"session_id": session, "input_id": "input-1", "update": update},
            "evidence": [{"file": "steps/0001/acp-events.jsonl", "line": line}]}


def said(seconds, line, text, **kwargs):
    return report(seconds, line, sessionUpdate="agent_message_chunk", content={"type": "text", "text": text}, **kwargs)


def test_the_network_clock_is_moved_back_by_the_measured_lead():
    assert clock(moment(1))["unix_nano"] - clock(moment(1), NETWORK_LEAD)["unix_nano"] == 140_000_000
    assert clock(moment(1), NETWORK_LEAD)["start_time"] == moment(0.86)
    assert clock("not a time") is None and clock("2026-01-01T00:00:00") is None and clock(None) is None


def test_a_model_call_is_identified_by_its_tool_call_ids_or_its_text():
    # The trace redacts arguments; the ids it emitted are still the wire's.
    exported = traced("m1", 1, calls=[("call-1", {"key": "[REDACTED]"})])
    sent = wired("n1", 1.1, calls=[("call-1", {"key": "secret"})])
    assert output_key(exported) == output_key(sent) == ("tool_calls", ("call-1",))
    assert output_key(traced("m2", 2, text=" done\n")) == output_key(wired("n2", 2.1, text="done")) == ("text", "done")
    assert output_key(traced("m3", 3, text="call-1")) != output_key(exported)


def test_equal_outputs_pair_in_recorded_order_and_the_rest_stay_alone():
    trace = [traced("m2", 5, text="ok"), traced("m1", 1, text="ok"), traced("m3", 7, text="only traced")]
    network = [wired("n2", 5.1, text="ok"), wired("n1", 1.1, text="ok"), wired("n3", 9, text="only wired")]
    assert [(a["id"], b["id"]) for a, b in pair_models(trace, network)] == [("m1", "n1"), ("m2", "n2")]


def test_merge_names_the_sources_of_every_record():
    m1, m2 = traced("m1", 1, calls=[("call-1", {})]), traced("m2", 3, text="done")
    exported_tool = tool("t1", "call-1")
    models, tools = [m1, m2], [exported_tool]
    network = [wired("n1", 1.1, calls=[("call-1", {})]), wired("n3", 5, calls=[("call-2", {})])]
    native = [report(1.5, 1, sessionUpdate="tool_call", toolCallId="call-1", title="read: a.txt", rawInput={"path": "a.txt"}),
              report(5.5, 2, sessionUpdate="tool_call", toolCallId="call-2", title="exec: ls", rawInput={"command": "ls"}),
              report(6.0, 3, sessionUpdate="tool_call_update", toolCallId="call-2", status="completed", rawOutput="a.txt"),
              said(7.0, 4, "do"), said(7.1, 5, "ne")]
    merge(models, tools, network, native)
    # The wire call both recorded is folded into the span's record, with the wire's evidence.
    assert [model["id"] for model in models] == ["m1", "m2", "n3"]
    assert m1["sources"] == [NETWORK, TRACE] and m1["call_id"] == "wire-n1"
    assert {ref["file"] for ref in m1["evidence"]} == {"otel/spans.jsonl", "logs/network.jsonl"}
    # Reply text sent over ACP is the text of the model call that produced it.
    assert m2["sources"] == [TRACE, ACP] and m2["native_session_id"] == "root-session"
    assert [ref["line"] for ref in m2["session_evidence"]] == [4, 5]
    assert models[2]["sources"] == [NETWORK] and models[2]["clock"]["start_time"] == moment(4.86)
    # A reported tool call the trace also exported is one execution; one only ACP reported is a record of its own.
    assert exported_tool["sources"] == [TRACE, ACP] and len(exported_tool["evidence"]) == 2
    reported = tools[1]
    assert (reported["sources"], reported["tool_call_id"], reported["tool_name"]) == ([ACP], "call-2", "exec: ls")
    assert (reported["input_arguments"], reported["outputs"], reported["execution_status"]) == ({"command": "ls"}, "a.txt", "succeeded")
    assert reported["native_session_id"] == "root-session" and reported["clock"]["start_time"] == moment(5.5)
    assert (reported["started_at"], reported["ended_at"]) == (moment(5.5), moment(6.0))


def test_an_unfinished_acp_tool_report_is_not_observed_to_end():
    (key, events), = acp_tool_reports([report(1, 1, sessionUpdate="tool_call", toolCallId="call-1", kind="execute",
                                              status="in_progress")]).items()
    reported = acp_tool(*key, events)
    assert (reported["execution_status"], reported["ended_at"], reported["tool_name"]) == ("not_observed", None, "execute")


def test_reply_text_two_model_calls_share_names_no_session():
    # A child may say what the root then repeats: the text alone cannot tell them apart.
    first, second = traced("m1", 1, text="391"), traced("m2", 2, text="391")
    models = [first, second]
    merge(models, [], [], [said(3, 1, "391")])
    assert first["sources"] == [TRACE, ACP] and second["sources"] == [TRACE]
    assert "native_session_id" not in first and "native_session_id" not in second


def test_reply_text_is_cut_at_tool_calls_and_prompt_boundaries():
    before, after = traced("m1", 1, text="looking", calls=[("call-1", {})]), traced("m2", 3, text="found it")
    models = [before, after]
    native = [said(1.2, 1, "looking"), report(1.5, 2, sessionUpdate="tool_call", toolCallId="call-1", title="read"),
              said(3.2, 3, "found "), said(3.3, 4, "it"),
              {"event": "prompt_completed", "timestamp": moment(4), "data": {}, "evidence": []}, said(5, 5, "late notice")]
    merge(models, [], [], native)
    assert before["sources"] == after["sources"] == [TRACE, ACP]
    assert [ref["line"] for ref in after["evidence"] if ref["file"].endswith("acp-events.jsonl")] == [3, 4]
