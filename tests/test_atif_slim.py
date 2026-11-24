"""The stored ATIF document keeps official fields and points into the attempt directory."""
import json

import pytest

from agentbench.trajectory.atif import attempt as atif_attempt
from agentbench.trajectory.atif.adapters import ADAPTER_NAMES
from agentbench.trajectory.atif.export import build_export
from agentbench.trajectory.atif.slim import check_pointers, slim, stored_document
from tests.atif_fixtures import fixture
from tests.test_atif_acp_otel import attempt as acp_attempt, call_span, reported, spawn_span, tool_span
from tests.test_atif_openclaw import export as openclaw_export, operation, spawn

# Copies of evidence the attempt directory already keeps.
DROPPED = {"raw_records", "invocations", "native_events", "unassigned_agent_spans", "auxiliary_artifacts",
           "model_record", "tool_execution", "record_ids", "recorded_usage", "invocation"}


def callback_layout(layout):
    def build(root):
        fixture(root, layout)
        return ()
    return build


def acp_otel(root):
    acp_attempt(root, [call_span(text="", calls=[("call-1", "read", {"path": "a.txt"})]),
                       tool_span(2, "call-1", "read", {"path": "a.txt"}, "77"), call_span(3, text="hi there")])
    return ()


def nested_delegation(root):
    openclaw_export(root, spawn("first", "run-1", "session-a"),
                    spawn("nested", "run-2", "session-b", parent="session-a"),
                    operation("read", "session-b", "read", {"path": "test.txt"}, "77"))
    return ADAPTER_NAMES


SCENARIOS = {"standalone": callback_layout("standalone"), "steps": callback_layout("steps"),
             "legacy": callback_layout("legacy"), "acp_otel": acp_otel,
             "nested_delegation": nested_delegation}


def built(tmp_path, name):
    adapters = SCENARIOS[name](tmp_path)
    result, _ = build_export(tmp_path, adapters=adapters)
    return result.document.to_json_dict()


def official(document):
    """The document without any ``extra``: what Harbor defines."""
    if isinstance(document, dict):
        return {key: official(value) for key, value in document.items() if key != "extra"}
    if isinstance(document, list):
        return [official(value) for value in document]
    return document


def abb_keys(document):
    found = set()
    if isinstance(document, dict):
        found |= set(((document.get("extra") or {}).get("abb") or {}))
        for value in document.values():
            found |= abb_keys(value)
    elif isinstance(document, list):
        for value in document:
            found |= abb_keys(value)
    return found


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_stored_form_keeps_official_fields_and_drops_copies(tmp_path, name):
    from harbor.utils.trajectory_validator import TrajectoryValidator
    full = built(tmp_path, name)
    stored = stored_document(full, tmp_path)
    assert official(stored) == official(full)
    assert not abb_keys(stored) & DROPPED
    assert len(json.dumps(stored)) < len(json.dumps(full))
    validator = TrajectoryValidator()
    assert validator.validate(stored), validator.get_errors()


def test_steps_point_to_the_records_they_came_from(tmp_path):
    stored = stored_document(built(tmp_path, "acp_otel"), tmp_path)
    assert stored["extra"]["abb"]["source"] == "acp_otel"
    user, first, second = stored["steps"]
    assert user["extra"]["abb"] == {"input_id": "input-1", "evidence": [{"file": "steps/0001/input.json", "line": None}]}
    assert first["extra"]["abb"]["evidence"] == [{"file": "otel/spans.jsonl", "line": 1}]
    assert second["extra"]["abb"]["evidence"] == [{"file": "otel/spans.jsonl", "line": 3}]
    result, = first["observation"]["results"]
    # One pointer, to the span the Agent exported for this execution, with that span's own clock.
    assert result["extra"]["abb"] == {"evidence": [{"file": "otel/spans.jsonl", "line": 2}],
                                      "execution_status": "succeeded",
                                      "started_at": result["extra"]["abb"]["started_at"],
                                      "ended_at": result["extra"]["abb"]["ended_at"]}
    assert "extra" not in first["metrics"]


def test_children_and_delegation_facts_keep_pointers(tmp_path):
    stored = stored_document(built(tmp_path, "nested_delegation"), tmp_path)
    first, = stored["subagent_trajectories"]
    nested, = first["subagent_trajectories"]
    assert nested["extra"]["abb"]["execution"]["key"]["native_id"] == "run-2"
    assert set(nested["extra"]["abb"]) == {"execution", "version_missing_reason"}
    facts = stored["extra"]["abb"]["delegation_facts"]
    assert len(facts) == 2 and all(fact["evidence"] for fact in facts)
    assert all(set(pointer) == {"file", "line"} for fact in facts for pointer in fact["evidence"])


def test_unassigned_record_keeps_a_summary_and_pointer(tmp_path):
    # The root spawns a child; the child's own inference names no session and stays unassigned.
    acp_attempt(tmp_path, [call_span(11, text="", calls=[("call-spawn", "sessions_spawn", {"task": "read"})], parent=10),
                           spawn_span(12, "call-spawn", "run-1", parent=10), call_span(21, text="77", parent=20)],
                sessions=([reported("root-session", "call-spawn")],))
    result, _ = build_export(tmp_path, adapters=["openclaw"])
    stored = stored_document(result.document, tmp_path)
    record, = stored["extra"]["abb"]["unassigned_records"]
    assert record == {"kind": "model", "source": "agent_native", "timestamp": record["timestamp"],
                      "evidence": [{"file": "otel/spans.jsonl", "line": 3}]}
    issue = next(i for i in stored["extra"]["abb"]["issues"] if i["code"] == "unassigned_record")
    assert issue["evidence"] == record["evidence"] and "subjects" not in issue


def test_an_unlisted_key_fails_instead_of_being_stored_or_lost(tmp_path):
    full = built(tmp_path, "steps")
    full["steps"][0]["extra"]["abb"]["new_detail"] = {"large": "value"}
    with pytest.raises(ValueError, match="new_detail has no storage rule"):
        slim(full, tmp_path)
    full = built(tmp_path, "steps")
    full["extra"]["other_tool"] = {}
    with pytest.raises(ValueError, match="outside the ABB namespace"):
        slim(full, tmp_path)


def test_a_pointer_that_opens_nothing_fails(tmp_path):
    stored = stored_document(built(tmp_path, "acp_otel"), tmp_path)
    stored["steps"][1]["extra"]["abb"]["evidence"] = [{"file": "otel/spans.jsonl", "line": 99}]
    with pytest.raises(ValueError, match="past the end"):
        check_pointers(stored, tmp_path)
    stored["steps"][1]["extra"]["abb"]["evidence"] = [{"file": "otel/missing.jsonl", "line": 1}]
    with pytest.raises(ValueError, match="missing evidence file"):
        check_pointers(stored, tmp_path)
    stored["steps"][1]["extra"]["abb"]["evidence"] = [{"file": "../run.json", "line": None}]
    with pytest.raises(ValueError, match="missing evidence file"):
        check_pointers(stored, tmp_path)


def test_the_run_flow_saves_the_stored_form(tmp_path):
    acp_otel(tmp_path)
    status = atif_attempt.write(tmp_path)
    saved = json.loads((tmp_path / "trajectory.atif.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete" and status["steps"] == len(saved["steps"])
    assert saved == stored_document(build_export(tmp_path)[0].document, tmp_path)
    assert not abb_keys(saved) & DROPPED
