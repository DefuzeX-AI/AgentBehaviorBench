from tests.atif_fixtures import fixture, child_bundle, lines, event, call, response
from agentbench.trajectory.atif.reader import read_evidence
from agentbench.trajectory.atif.export import build_export
from agentbench.trajectory.atif.hierarchy import resolve_hierarchy
from agentbench.trajectory.atif.assembler import assemble_atif
from agentbench.trajectory.atif.provenance import provenance
from agentbench.trajectory.atif.validation import walk


def test_official_model_tool_usage_context_and_result_boundary(tmp_path):
    fixture(tmp_path)
    result, _ = build_export(tmp_path)
    steps = result.document.steps
    models = [s for s in steps if s.llm_call_count == 1]
    assert len(models) == 1 # Runtime result is not another assistant reply.
    model = models[0]
    assert model.tool_calls is None
    assert model.metrics is None and model.model_name is None
    assert model.extra["abb"]["model_record"]["source"] == "framework"
    tool = next(s for s in steps if s.observation).observation.results[0]
    assert tool.content == "42"
    assert tool.extra["abb"]["tool_execution"]["input_arguments"] == {"a": 19, "b": 23}
    wire = read_evidence(tmp_path).models[0]
    assert wire["output"]["usage"]["prompt_tokens"] == 7
    assert wire["output"]["model"] == "observed-model"



def test_identical_text_from_two_executions_is_preserved(tmp_path):
    bundle = child_bundle(tmp_path)
    graph = resolve_hierarchy(bundle, adapters=["deepagents"])
    doc = assemble_atif(bundle, graph, provenance(bundle))
    assert sum(s.message == "identical text" for d in walk(doc) for s in d.steps) == 2
    assert len(doc.subagent_trajectories) == 2
    assert all([s.step_id for s in d.steps] == list(range(1, len(d.steps)+1)) for d in walk(doc))


def test_partial_stream_and_incomplete_json_survive(tmp_path):
    fixture(tmp_path, tool=False)
    lines(tmp_path / "network.jsonl", [event("llm_request", call_id="wire-1", framework_span_id="model", payload={}),
        event("llm_delta", call_id="wire-1", sequence=1, payload={"choices": [{"delta": {
            "content": "半途 español", "tool_calls": [{"index": 0, **call(args='{"a":')}]}}]})])
    result, _ = build_export(tmp_path)
    model = next(s for s in result.document.steps if s.llm_call_count == 1)
    assert model.message == "你好 ¡España!"
    wire = read_evidence(tmp_path).models[0]
    assert wire["output"]["text"] == "半途 español"
    assert not model.tool_calls
    assert wire["output"]["tool_calls"][0]["arguments"] == '{"a":'
    assert wire["status"] == "incomplete"


def test_tool_errors_and_unobserved_result_do_not_become_success(tmp_path):
    folder = fixture(tmp_path)
    import json
    rows = [json.loads(line) for line in (folder / "framework.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[-1] = event("span_error", span_id="tool", error="permission denied")
    lines(folder / "framework.jsonl", rows)
    result, _ = build_export(tmp_path)
    observation = next(s for s in result.document.steps if s.observation).observation.results[0]
    assert observation.extra["abb"]["tool_execution"]["execution_status"] == "error"
    assert observation.content == "permission denied"


def test_empty_partial_arguments_are_not_fabricated_as_empty_object(tmp_path):
    fixture(tmp_path, tool=False)
    lines(tmp_path / "network.jsonl", [event("llm_request", call_id="wire-1", framework_span_id="model", payload={}),
        event("llm_delta", call_id="wire-1", sequence=1, payload={"choices": [{"delta": {
            "tool_calls": [{"index": 0, **call(args="")}]}}]})])
    result, _ = build_export(tmp_path)
    step = next(s for s in result.document.steps if s.llm_call_count == 1)
    assert not step.tool_calls
    assert read_evidence(tmp_path).models[0]["output"]["tool_calls"][0]["arguments"] == ""


def test_known_execution_unlinked_tool_is_retained_without_fake_model(tmp_path):
    fixture(tmp_path)
    lines(tmp_path / "network.jsonl", [])
    result, _ = build_export(tmp_path)
    independent = [s for s in result.document.steps if (s.extra or {}).get("abb", {}).get("kind") == "independent_tool"]
    assert len(independent) == 1
    assert independent[0].llm_call_count is None
    assert independent[0].observation.results[0].source_call_id is None


def test_numbered_turns_and_identical_deliveries(tmp_path):
    from tests.atif_fixtures import save
    folder = fixture(tmp_path, layout="steps", tool=False)
    # Keep only unowned model evidence to exercise the user-visible projection.
    lines(folder / "framework.jsonl", [])
    for i in range(1, 12):
        directory = folder.parent / f"{i:04d}"
        save(directory / "input.json", {"input_id": str(i), "payload": str(i)})
        save(directory / "result.json", {"input_id": str(i), "output": "Hola", "status": "succeeded"})
    result, _ = build_export(tmp_path)
    assert [(s.source, s.message) for s in result.document.steps] == [
        pair for i in range(1, 12) for pair in [("user", str(i)), ("agent", "Hola")]]
    assert result.validation["observed_models"] == result.validation["unassigned_records"] == 0
    assert len(read_evidence(tmp_path).models) == 1


def test_only_confirmed_reply_is_projected(tmp_path):
    from tests.atif_fixtures import save
    folder = fixture(tmp_path, layout="steps")
    for result in ({"status": "cancelled", "output": "partial"},
                   {"status": "failed", "output": "error"},
                   {"status": "succeeded", "input_id": "other", "output": "wrong turn"},
                   {"status": "succeeded", "output": {"debug": "internal state"}}):
        save(folder / "result.json", result)
        exported, _ = build_export(tmp_path)
        assert all("result_source" not in s.extra["abb"] for s in exported.document.steps if s.extra)


def test_final_provider_response_ref_reuses_root_model_step():
    from pathlib import Path
    exported, bundle = build_export(Path(__file__).parent / "fixtures/atif/two_children", adapters=["deepagents"])
    answer = bundle.inputs[0]["result"]["output"]
    delivered = [s for s in exported.document.steps if s.message == answer]
    assert len(delivered) == 1
    assert delivered[0].llm_call_count == 1
    assert delivered[0].extra["abb"]["result_source"].endswith("/result.json")
