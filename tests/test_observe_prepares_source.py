"""observe must materialize install/git sources before building the Agent image, like run/evaluate."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.observe import service


def test_observe_prepares_agent_source_before_any_artifact(tmp_path, monkeypatch):
    unit = tmp_path / "unit"
    unit.mkdir()
    (unit / "agent.toml").write_text("", encoding="utf-8")
    calls = []

    def prepare(root, **kwargs):
        calls.append(Path(root))
        raise RuntimeError("source prepared")

    monkeypatch.setattr(service, "runtime_type", lambda path: "docker")
    monkeypatch.setattr(service, "execution_strategy", lambda path: "oneshot")
    monkeypatch.setattr(service, "prepare_agent_source", prepare)
    output = tmp_path / "observe"
    with pytest.raises(RuntimeError, match="source prepared"):
        service.observe(SimpleNamespace(path=unit, agent_id="demo"), "hi", output=output, environ={})
    assert calls == [unit]
    assert not output.exists()


def test_observe_materializes_an_install_unit(tmp_path, monkeypatch):
    unit = tmp_path / "unit"
    (unit / "install").mkdir(parents=True)
    (unit / "install" / "package.json").write_text('{"name": "demo"}', encoding="utf-8")
    (unit / "requirement.md").write_text("demo", encoding="utf-8")
    (unit / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (unit / "agent.toml").write_text(
        '[source]\nmethod = "install"\nrepository = "https://example.com/demo"\n'
        'revision = "0000000000000000000000000000000000000000"\n'
        '[runtime]\ntype = "docker"\nexecution = "oneshot"\n[build]\ncontext = "."\ndockerfile = "Dockerfile"\n',
        encoding="utf-8")

    class Stop(Exception):
        pass

    def runtime(**kwargs):
        raise Stop

    monkeypatch.setattr(service, "DockerRuntime", runtime)
    monkeypatch.setattr("agentbench.runtime.source.preparation.docker_structure", lambda root, manifest: None)
    with pytest.raises(Stop):
        service.observe(SimpleNamespace(path=unit, agent_id="demo"), "hi", output=tmp_path / "out", environ={})
    assert (unit / "agent" / "package.json").read_text(encoding="utf-8") == '{"name": "demo"}'
