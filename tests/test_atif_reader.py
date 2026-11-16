from tests.atif_fixtures import fixture, save, lines, event
from agentbench.trajectory.atif.reader import read_evidence
import pytest


@pytest.mark.parametrize("layout", ["standalone", "steps", "legacy"])
def test_layout_input_and_full_raw_records(tmp_path, layout):
    fixture(tmp_path, layout)
    bundle = read_evidence(tmp_path)
    assert bundle.inputs[0]["record"]["payload"] == "你好 ¡España!"
    assert len(bundle.models) == len(bundle.tools) == 1
    assert len(bundle.spans) == 3
    assert bundle.models[0]["source"] == "wire+framework"
    assert bundle.models[0]["input"]["model"] == "configured-model"
    assert bundle.models[0]["output"]["model"] == "observed-model"


def test_old_flat_trajectory_never_used(tmp_path):
    fixture(tmp_path)
    save(tmp_path / "trajectory.json", {"steps": [{"output": "wrong old output"}]})
    assert read_evidence(tmp_path).models[0]["output"]["text"] == "你好 ¡España!"


def test_unfinished_requires_explicit_opt_in(tmp_path):
    fixture(tmp_path, finished=False)
    with pytest.raises(ValueError, match="allow-incomplete"):
        read_evidence(tmp_path)
    assert any(i.code == "incomplete_run" for i in read_evidence(tmp_path, allow_incomplete=True).issues)


def test_missing_native_and_version_are_not_replaced_by_registry(tmp_path):
    fixture(tmp_path)
    (tmp_path / "request/target.json").unlink()
    assert read_evidence(tmp_path).target == {}


def test_retries_keep_two_wire_attempts_not_two_callback_answers(tmp_path):
    fixture(tmp_path, tool=False)
    lines(tmp_path / "network.jsonl", [event("llm_request", call_id=cid, framework_span_id="model", payload={})
        for cid in ("retry-1", "retry-2")])
    bundle = read_evidence(tmp_path)
    assert len(bundle.models) == 2
    assert all(m["output"].get("text") in (None, "") for m in bundle.models)
    assert all(m.get("shared_framework_output") for m in bundle.models)


def test_incomplete_raw_line_is_preserved_as_evidence(tmp_path):
    fixture(tmp_path)
    with (tmp_path / "network.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"event":"llm_delta","data":')
    bundle = read_evidence(tmp_path)
    assert any(r["raw"].get("unparsed_line") == '{"event":"llm_delta","data":' for r in bundle.raw_records)
    assert any(i.code == "invalid_raw_record" for i in bundle.issues)
