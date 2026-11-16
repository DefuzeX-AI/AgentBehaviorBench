from pathlib import Path
import json
from tests.atif_fixtures import fixture
from agentbench.trajectory.atif.export import build_export, export_run
from agentbench.trajectory.atif.validation import walk
from agentbench.experiments.atif.acceptance import content_checks, verify


def test_real_history_11_models_12_tools_two_distinct_children_and_59_checks():
    root = Path(__file__).parent / "fixtures/atif/two_children"
    result, bundle = build_export(root, adapters=["deepagents"])
    doc = result.document
    assert result.validation["observed_models"] == 11
    assert result.validation["observed_tools"] == 12
    assert result.validation["unassigned_records"] == 0
    assert sum(s.llm_call_count == 1 for s in doc.steps) == 3
    assert [sum(s.llm_call_count == 1 for s in c.steps) for c in doc.subagent_trajectories] == [4, 4]
    refs = [r.trajectory_id for s in doc.steps if s.observation for o in s.observation.results for r in o.subagent_trajectory_ref or []]
    assert len(refs) == 2 and len(set(refs)) == 2
    assert set(refs) == {c.trajectory_id for c in doc.subagent_trajectories}
    checks = content_checks(bundle, doc)
    assert len(checks) == 59
    assert all(c["passed"] for c in checks)


def test_verify_detects_edited_trajectory(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    destination = tmp_path / "export"
    export_run(source, destination)
    assert verify(source, destination)["passed"]
    path = destination / "trajectory.atif.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["steps"][-1]["message"] = "edited"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert not verify(source, destination)["passed"]
