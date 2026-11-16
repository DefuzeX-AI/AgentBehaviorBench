import json
from tests.atif_fixtures import fixture, save
from agentbench.trajectory.atif.export import export_run, build_export
from agentbench.trajectory.atif.provenance import snapshot
import pytest


def test_utf8_determinism_and_source_immutability(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    before = snapshot(source)
    a = export_run(source, tmp_path / "a")
    b = export_run(source, tmp_path / "b")
    assert (tmp_path / "a/trajectory.atif.json").read_bytes() == (tmp_path / "b/trajectory.atif.json").read_bytes()
    assert "¡España!" in (tmp_path / "a/trajectory.atif.json").read_text(encoding="utf-8")
    assert snapshot(source) == before
    assert a.document.trajectory_id == b.document.trajectory_id


def test_missing_history_version_is_unknown(tmp_path):
    fixture(tmp_path)
    (tmp_path / "request/target.json").unlink()
    result, _ = build_export(tmp_path)
    assert result.document.agent.version == "unknown"
    assert any(i["code"] == "missing_agent_revision" for i in result.validation["issues"])


def test_empty_source_does_not_forge_step(tmp_path):
    source = tmp_path / "source"
    save(source / "run.json", {"run_id": "empty", "status": "succeeded"})
    save(source / "trajectory.json", {"steps": [{"message": "old"}]})
    with pytest.raises(ValueError, match="No observed steps"):
        export_run(source, tmp_path / "export")
    assert not (tmp_path / "export/trajectory.atif.json").exists()
    assert json.loads((tmp_path / "export/validation-report.json").read_text())["status"] == "failed"


def test_mutating_source_aborts_publication(tmp_path, monkeypatch):
    import agentbench.trajectory.atif.export as module
    source = tmp_path / "source"
    fixture(source)
    original = module.assemble_atif
    def mutate(*args):
        doc = original(*args)
        save(source / "run.json", {"run_id": "changed", "status": "succeeded"})
        return doc
    monkeypatch.setattr(module, "assemble_atif", mutate)
    with pytest.raises(ValueError, match="changed"):
        export_run(source, tmp_path / "export")
    assert not (tmp_path / "export/trajectory.atif.json").exists()


def test_refuses_overwrite_or_source_directory(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    with pytest.raises(ValueError, match="separate"):
        export_run(source, source / "export")
    destination = tmp_path / "destination"
    save(destination / "keep.json", {"keep": True})
    with pytest.raises(ValueError, match="new or empty"):
        export_run(source, destination)


def test_linked_evidence_is_rejected(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    (source / "run.json").unlink()
    save(tmp_path / "outside.json", {"status": "succeeded"})
    (source / "run.json").symlink_to(tmp_path / "outside.json")
    with pytest.raises((ValueError, FileNotFoundError)):
        export_run(source, tmp_path / "export")
