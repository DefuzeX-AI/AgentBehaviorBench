"""An ACP Agent's steps come from the spans it exported, and from nothing ABB wrote."""
import json

import pytest

from agentbench.trajectory.agent_otel import inference, operations
from agentbench.trajectory.atif.export import build_export
from agentbench.trajectory.atif.sources import declared, select
from tests.atif_fixtures import event, lines, save, span


def exported_span(name, ordinal, *, parent=None, **attributes):
    values = {key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
              for key, value in attributes.items()}
    body = {"traceId": "aa" * 16, "spanId": f"{ordinal:016x}", "name": name,
            "startTimeUnixNano": str(1_700_000_000_000_000_000 + ordinal),
            "endTimeUnixNano": str(1_700_000_000_000_000_500 + ordinal),
            "attributes": [{"key": key, "value": {"stringValue": value}} for key, value in values.items()]}
    if parent is not None:
        body["parentSpanId"] = f"{parent:016x}"
    return {"schema": "abb.agent-otel.v1", "origin": "agent_native", "resource": {}, "scope": {"name": "target"},
            "span": body}


def call_span(ordinal=1, *, text="hi there", calls=(), parent=None, **attributes):
    parts = [{"type": "text", "content": text},
             *({"type": "tool_call", "id": cid, "name": name, "arguments": arguments} for cid, name, arguments in calls)]
    return exported_span("target.model.call", ordinal, parent=parent, **{
        "gen_ai.operation.name": "text_completion", "gen_ai.request.model": "observed-model",
        "gen_ai.usage.input_tokens": "120", "gen_ai.usage.output_tokens": "9",
        "gen_ai.usage.cache_read.input_tokens": "20",
        "gen_ai.input.messages": [{"role": "user", "parts": [{"type": "text", "content": "hello"}]}],
        "gen_ai.output.messages": [{"role": "assistant", "parts": parts, "finish_reason": "stop"}], **attributes})


def tool_span(ordinal, call_id, name, arguments, result, *, parent=None):
    return exported_span("target.tool.execution", ordinal, parent=parent, **{
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name, "gen_ai.tool.call.id": call_id,
        "gen_ai.tool.call.arguments": arguments, "gen_ai.tool.call.result": result})


USAGE_SUMMARY = exported_span("target.model.usage", 9, **{"gen_ai.operation.name": "chat",
                                                          "gen_ai.usage.input_tokens": "120"})


def reported(session, call_id):
    """The ACP message in which the Agent reported one tool call of a session."""
    return event("session_update", session_id=session, update={"sessionUpdate": "tool_call", "toolCallId": call_id})


def attempt(root, spans, *, adapter="acp", scoped=True, framework=(), inputs=("hello",), sessions=()):
    """Answered Inputs of an ACP Agent; ``sessions`` lists each Input's ACP tool reports."""
    save(root / "run.json", {"run_id": "run-a", "agent_id": "target", "status": "succeeded"})
    runtime = {"evaluation": {"single_input_model_scope": True} if scoped else {}}
    if adapter:
        runtime["adapter"] = {"type": adapter}
    save(root / "request/target.json", {"architecture": {"source_revision": "frozen"}, "runtime": runtime})
    folders = []
    for number, payload in enumerate(inputs, 1):
        folder = root / f"steps/{number:04d}"
        save(folder / "input.json", {"payload": payload, "input_id": f"input-{number}"})
        save(folder / "result.json", {"status": "succeeded", "output": "delivered text"})
        lines(folder / "framework.jsonl", [event("execution_start", input=payload), *(framework if number == 1 else ())])
        if sessions:
            save(folder / "acp-summary.json", {"session": {"sessionId": "root-session"}})
            lines(folder / "acp-events.jsonl", list(sessions[number - 1]))
        folders.append(folder)
    lines(root / "otel/spans.jsonl", spans)
    return folders[0]


def steps(document):
    return [(step.source, step.message, (step.extra or {}).get("abb", {}).get("kind")) for step in document.steps]


def test_the_adapter_type_selects_the_source():
    assert declared({"runtime": {"adapter": {"type": "acp"}}}) == "acp_otel"
    assert declared({"runtime": {"adapter": {"type": "langgraph"}}}) == "langgraph"
    assert declared({}) == "langgraph"  # attempts saved before the adapter type was recorded
    # A standalone observe run freezes no target; its invocation requests name the framework.
    assert declared({}, [{"request": {"framework": "acp"}}, {"request": None}]) == "acp_otel"
    assert declared({"runtime": {"adapter": {"type": "langgraph"}}}, [{"request": {"framework": "acp"}}]) == "langgraph"
    assert declared({"runtime": {"adapter": {"type": "acp"}, "atif": {"source": "langgraph"}}}) == "langgraph"
    with pytest.raises(ValueError, match="No ATIF step source for adapter type 'grpc'"):
        declared({"runtime": {"adapter": {"type": "grpc"}}})
    with pytest.raises(ValueError, match="Unknown ATIF step source 'whip'"):
        select("whip")
    assert (select("acp_otel").reply_steps, select("langgraph").reply_steps) == (False, True)


def test_inference_reads_messages_tool_calls_and_usage():
    row = call_span(calls=[("call-1", "read", json.dumps({"path": "a.txt"}))], **{
        "gen_ai.tool.definitions": [{"type": "function", "name": "read"}]})
    item, = operations([{"file": "otel/spans.jsonl", "line": 1, "raw": row}])
    values = inference(item)
    assert values["output"] == {"text": "hi there", "reasoning": None, "finish_reason": "stop", "model": "observed-model",
                                "tool_calls": [{"id": "call-1", "name": "read", "arguments": {"path": "a.txt"}}],
                                "usage": {"prompt_tokens": 120, "completion_tokens": 9,
                                          "prompt_tokens_details": {"cached_tokens": 20}}}
    assert values["input"]["messages"][0]["role"] == "user" and values["input"]["tools"][0]["name"] == "read"
    summary, = operations([{"file": "otel/spans.jsonl", "line": 2, "raw": USAGE_SUMMARY}])
    assert summary["kind"] == "model" and inference(summary) is None


def test_the_last_model_step_is_the_reply(tmp_path):
    attempt(tmp_path, [call_span(), USAGE_SUMMARY])
    result, _ = build_export(tmp_path)
    document = result.document
    # The delivered result is not repeated as a step of its own.
    assert steps(document) == [("user", "hello", None), ("agent", "hi there", None)]
    model = document.steps[1]
    assert model.model_name == "observed-model" and model.llm_call_count == 1
    assert (model.metrics.prompt_tokens, model.metrics.completion_tokens, model.metrics.cached_tokens) == (120, 9, 20)
    assert model.timestamp is not None and model.extra["abb"]["turn_evidence"] == "isolated_single_input_case"
    assert document.final_metrics.total_prompt_tokens == 120 and document.extra["abb"]["source"] == "acp_otel"
    assert result.validation["status"] == "complete" and result.validation["observed_models"] == 1
    # The aggregate usage span repeats no call and stays visible as unassigned evidence.
    assert [item["name"] for item in document.extra["abb"]["unassigned_agent_spans"]] == ["target.model.usage"]


def test_tool_results_come_from_the_exported_tool_span(tmp_path):
    # ABB's ACP observer wrote its own tool span with another output; it is not read.
    observer = [span("root"), span("tool", "root", "tool", "read", input={"path": "a.txt"}, tool_call_id="call-1"),
                event("span_end", span_id="tool", output="written by the observer")]
    attempt(tmp_path, [call_span(text="", calls=[("call-1", "read", {"path": "a.txt"})]),
                       tool_span(2, "call-1", "read", {"path": "a.txt"}, "77"),
                       call_span(3, text="hi there")], framework=observer)
    result, _ = build_export(tmp_path)
    first, second = result.document.steps[1], result.document.steps[2]
    assert [(call.tool_call_id, call.function_name, call.arguments) for call in first.tool_calls] == [
        ("call-1", "read", {"path": "a.txt"})]
    observed, = first.observation.results
    assert observed.source_call_id == "call-1" and observed.content == "77"
    execution = observed.extra["abb"]["tool_execution"]
    assert execution["source"] == "agent_native" and execution["execution_status"] == "succeeded"
    assert [ref["file"] for ref in execution["evidence"]] == ["otel/spans.jsonl"]
    assert second.message == "hi there" and not second.tool_calls
    assert result.validation["observed_tools"] == 1 and len(result.document.steps) == 3


def test_an_agent_without_exported_inference_has_no_model_step(tmp_path):
    observer = [span("root"), span("tool", "root", "tool", "read", input={}, tool_call_id="call-1"),
                event("span_end", span_id="tool", output="77")]
    attempt(tmp_path, [USAGE_SUMMARY], framework=observer)
    result, _ = build_export(tmp_path)
    assert steps(result.document) == [("user", "hello", None)]
    assert result.validation["status"] == "partial"
    assert "agent_otel_models_missing" in [issue["code"] for issue in result.validation["issues"]]


def test_without_a_declared_scope_or_session_the_step_follows_the_turn(tmp_path):
    attempt(tmp_path, [call_span()], scoped=False)
    document = build_export(tmp_path)[0].document
    assert steps(document) == [("user", "hello", None), ("agent", "hi there", None)]
    assert "turn_evidence" not in document.steps[1].extra["abb"]


def test_acp_tool_reports_place_each_run_in_its_own_turn(tmp_path):
    # Two prompts, each one run of the Agent: a parent span with a model call, its tool and the answer.
    first = [call_span(11, text="", calls=[("call-a", "read", {})], parent=10), tool_span(12, "call-a", "read", {}, "A", parent=10),
             call_span(13, text="first answer", parent=10)]
    second = [call_span(21, text="", calls=[("call-b", "read", {})], parent=20), tool_span(22, "call-b", "read", {}, "B", parent=20),
              call_span(23, text="second answer", parent=20)]
    runs = [exported_span("target.run", 10), exported_span("target.run", 20)]
    attempt(tmp_path, [*second, *first, *runs], scoped=False, inputs=("one", "two"),
            sessions=([reported("root-session", "call-a")], [reported("root-session", "call-b")]))
    result, _ = build_export(tmp_path)
    assert [(step.source, step.message) for step in result.document.steps] == [
        ("user", "one"), ("agent", ""), ("agent", "first answer"),
        ("user", "two"), ("agent", ""), ("agent", "second answer")]
    assert result.validation["status"] == "complete"
    # The answer names no tool call; it shares the run's parent span with the reported one.
    answer = result.document.steps[2].extra["abb"]["model_record"]
    assert answer["native_session_id"] == "root-session"


def test_a_missing_parent_span_reports_an_incomplete_export(tmp_path):
    # The run span is exported last, when the run ends. Without it the run's tail may be absent too.
    attempt(tmp_path, [call_span(11, text="", calls=[("call-a", "read", {})], parent=10),
                       tool_span(12, "call-a", "read", {}, "A", parent=10)])
    result, _ = build_export(tmp_path)
    issue, = [issue for issue in result.validation["issues"] if issue["code"] == "agent_otel_export_incomplete"]
    assert len(issue["record_ids"]) == 2 and result.validation["status"] == "partial"
    assert steps(result.document) == [("user", "hello", None), ("agent", "", None)]


def test_callbacks_stay_the_step_record_of_a_langgraph_agent(tmp_path):
    callbacks = [span("root"), span("model", "root", "llm", "model", input={}),
                 event("span_end", span_id="model",
                       output={"generations": [[{"message": {"content": "hi there", "type": "ai"}}]]})]
    attempt(tmp_path, [call_span()], adapter="langgraph", framework=callbacks)
    result, _ = build_export(tmp_path)
    assert result.validation["observed_models"] == 1 and result.document.extra["abb"]["source"] == "langgraph"
    assert [item["name"] for item in result.document.extra["abb"]["unassigned_agent_spans"]] == ["target.model.call"]
    # The delivered result keeps its own step where callbacks are the record.
    assert steps(result.document)[-1] == ("agent", "delivered text", "invocation_result")


def spawn_span(ordinal, call_id, run, *, parent=None, context="isolated"):
    receipt = {"status": "accepted", "runId": run, "childSessionKey": "[REDACTED]", "context": context}
    return tool_span(ordinal, call_id, "sessions_spawn", {"task": "read number.txt"}, {"details": receipt}, parent=parent)


def test_a_spawn_reported_by_the_root_session_embeds_its_child(tmp_path):
    root_run = [call_span(11, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read number.txt"})], parent=10),
                spawn_span(12, "call-spawn", "run-1", parent=10)]
    # The child run exported its own operations; no recorded identifier names its run.
    child_run = [call_span(21, text="", calls=[("call-read", "read", {})], parent=20),
                 tool_span(22, "call-read", "read", {}, "77", parent=20), call_span(23, text="77", parent=20)]
    attempt(tmp_path, [*root_run, *child_run], sessions=([reported("root-session", "call-spawn")],))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    document = result.document
    assert [(step.source, step.message) for step in document.steps] == [("user", "hello"), ("agent", "")]
    child, = document.subagent_trajectories
    spawned, = document.steps[1].observation.results
    assert spawned.subagent_trajectory_ref[0].trajectory_id == child.trajectory_id
    assert [(step.source, step.message) for step in child.steps] == [("user", "read number.txt")]
    # Never guessed into the child: its three operations stay listed as unassigned.
    unassigned = document.extra["abb"]["unassigned_records"]
    assert sorted(record["kind"] for record in unassigned) == ["model", "model", "tool"]
    assert result.validation["status"] == "partial"


def test_without_an_acp_report_a_delegation_leaves_exported_records_unowned(tmp_path):
    attempt(tmp_path, [call_span(1, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read number.txt"})]),
                       spawn_span(2, "call-spawn", "run-1")])
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    assert not result.document.subagent_trajectories
    assert sorted(record["kind"] for record in result.document.extra["abb"]["unassigned_records"]) == ["model", "tool"]
    assert "invalid_delegation" in [issue["code"] for issue in result.validation["issues"]]


def openclaw_run(run, harness, *, under, operations):
    """One OpenClaw run as diagnostics-otel exports it: harness span, run span, operations."""
    return [exported_span("openclaw.harness.run", harness, parent=under),
            exported_span("openclaw.run", run, parent=harness), *operations]


def reading_child(run, harness, *, under, call_id="call-read", answer="77"):
    return openclaw_run(run, harness, under=under, operations=[
        call_span(run + 1, text="", calls=[(call_id, "read", {})], parent=run),
        tool_span(run + 2, call_id, "read", {}, answer, parent=run), call_span(run + 3, text=answer, parent=run)])


def trajectory_steps(trajectory):
    return [(step.source, step.message) for step in trajectory.steps]


def test_openclaw_run_structure_places_a_child_run_in_its_trajectory(tmp_path):
    # The spans name no session. The child's harness span is a child of the spawning run's harness span.
    root_run = openclaw_run(10, 2, under=1, operations=[
        call_span(11, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read number.txt"})], parent=10),
        spawn_span(12, "call-spawn", "run-1", parent=10), call_span(13, text="the child read 77", parent=10)])
    attempt(tmp_path, [exported_span("openclaw.message.processed", 1), *root_run, *reading_child(20, 3, under=2)],
            sessions=([reported("root-session", "call-spawn")],))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    document = result.document
    assert trajectory_steps(document) == [("user", "hello"), ("agent", ""), ("agent", "the child read 77")]
    child, = document.subagent_trajectories
    assert trajectory_steps(child) == [("user", "read number.txt"), ("agent", ""), ("agent", "77")]
    read, = child.steps[1].observation.results
    assert read.source_call_id == "call-read" and read.content == "77"
    assert not document.extra["abb"]["unassigned_records"] and result.validation["status"] == "complete"
    fact, = result.association["delegation_facts"]
    assert fact["attribution"] == "run_structure"
    # The fact cites the child's run and harness spans beside the spawn receipt.
    assert {(ref["file"], ref["line"]) for ref in fact["evidence"]} >= {("otel/spans.jsonl", 7), ("otel/spans.jsonl", 8)}


def test_two_spawns_in_one_run_are_never_paired_by_structure(tmp_path):
    root_run = openclaw_run(10, 2, under=1, operations=[
        call_span(11, text="", calls=[("call-a", "sessions_spawn", {"task": "read a"}),
                                      ("call-b", "sessions_spawn", {"task": "read b"})], parent=10),
        spawn_span(12, "call-a", "run-a", parent=10), spawn_span(13, "call-b", "run-b", parent=10)])
    spans = [exported_span("openclaw.message.processed", 1), *root_run,
             *reading_child(20, 3, under=2, call_id="read-a"), *reading_child(30, 4, under=2, call_id="read-b")]
    attempt(tmp_path, spans, sessions=([reported("root-session", "call-a"), reported("root-session", "call-b")],))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    children = result.document.subagent_trajectories
    assert sorted(trajectory_steps(child) for child in children) == [[("user", "read number.txt")]] * 2
    assert len(result.document.extra["abb"]["unassigned_records"]) == 6
    assert [issue["code"] for issue in result.validation["issues"]].count("openclaw_child_run_ambiguous") == 2


def test_a_child_run_that_spawns_again_nests_its_own_child(tmp_path):
    root_run = openclaw_run(10, 2, under=1, operations=[
        call_span(11, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read number.txt"})], parent=10),
        spawn_span(12, "call-spawn", "run-1", parent=10)])
    child_run = openclaw_run(20, 3, under=2, operations=[
        call_span(21, text="", calls=[("call-deeper", "sessions_spawn", {"task": "read number.txt"})], parent=20),
        spawn_span(22, "call-deeper", "run-2", parent=20)])
    spans = [exported_span("openclaw.message.processed", 1), *root_run, *child_run, *reading_child(30, 4, under=3)]
    # Only the root's spawn is reported over ACP; the child's own spawn is not.
    attempt(tmp_path, spans, sessions=([reported("root-session", "call-spawn")],))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    child, = result.document.subagent_trajectories
    grandchild, = child.subagent_trajectories
    assert trajectory_steps(child) == [("user", "read number.txt"), ("agent", "")]
    assert trajectory_steps(grandchild) == [("user", "read number.txt"), ("agent", ""), ("agent", "77")]
    assert not result.document.extra["abb"]["unassigned_records"] and result.validation["status"] == "complete"


def completion_notice(run, harness, *, under, replayed_call):
    """OpenClaw tells the requester its child finished: a further run of the requester's own
    conversation, whose input replays the earlier tool calls with ids reduced to letters and digits."""
    history = [{"role": "assistant", "parts": [{"type": "tool_call", "id": replayed_call, "name": "sessions_spawn"}]},
               {"role": "user", "parts": [{"type": "text", "content": "A background task completed."}]}]
    return openclaw_run(run, harness, under=under, operations=[
        call_span(run + 1, text="NO_REPLY", parent=run, **{"gen_ai.input.messages": history})])


def delegating_attempt(tmp_path, *, context):
    root_run = openclaw_run(10, 2, under=1, operations=[
        call_span(11, text="", calls=[("call_00_spawn", "sessions_spawn", {"task": "read number.txt"})], parent=10),
        spawn_span(12, "call_00_spawn", "run-1", parent=10, context=context),
        call_span(13, text="the child read 77", parent=10)])
    spans = [exported_span("openclaw.message.processed", 1), *root_run, *reading_child(20, 3, under=2),
             *completion_notice(30, 4, under=2, replayed_call="call00spawn")]
    attempt(tmp_path, spans, sessions=([reported("root-session", "call_00_spawn")],))
    return build_export(tmp_path, adapters=["openclaw"])[0]


def test_a_completion_notice_continues_the_requester_and_is_not_a_child(tmp_path):
    result = delegating_attempt(tmp_path, context="isolated")
    document = result.document
    # The notice is a further step of the root, placed in its turn by the root session.
    assert trajectory_steps(document) == [("user", "hello"), ("agent", ""), ("agent", "the child read 77"),
                                          ("agent", "NO_REPLY")]
    assert document.steps[3].extra["abb"]["model_record"]["native_session_id"] == "root-session"
    child, = document.subagent_trajectories
    assert trajectory_steps(child) == [("user", "read number.txt"), ("agent", ""), ("agent", "77")]
    assert not document.extra["abb"]["unassigned_records"] and result.validation["status"] == "complete"


def test_a_child_that_inherits_the_conversation_cannot_be_told_from_a_notice(tmp_path):
    result = delegating_attempt(tmp_path, context="fork")
    child, = result.document.subagent_trajectories
    assert trajectory_steps(child) == [("user", "read number.txt")]
    assert len(result.document.extra["abb"]["unassigned_records"]) == 4
    assert "openclaw_child_run_ambiguous" in [issue["code"] for issue in result.validation["issues"]]
