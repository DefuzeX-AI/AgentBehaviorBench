"""`agentbench agent delete`: unregister one unit and archive its folder recoverably."""

from __future__ import annotations

import builtins
import shutil
from pathlib import Path

import pytest

from agentbench.cli.main import cli
from agentbench.harness.registry import load_registry, tomllib


def _unit(agents: Path, folder: str, agent_id: str) -> Path:
    unit = agents / folder
    (unit / "ground_truth").mkdir(parents=True)
    (unit / "ground_truth" / ".gitkeep").write_bytes(b"")
    (unit / "agent.toml").write_text(
        f'agent_id = "{agent_id}"\nframework = "langgraph"\n', encoding="utf-8")
    (unit / "requirement.md").write_text("Echo the input.\n", encoding="utf-8")
    return unit


REGISTRY = """schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "alpha"
path = "resources/agents/01-alpha"
enabled = true
status = "ready"
framework = "langgraph"
source = "https://github.com/example/alpha"
case = 1

[[agents]]
agent_id = "beta"
path = "resources/agents/02-beta"
enabled = false
status = "adapting"
framework = "langgraph"
source = "https://github.com/example/beta"
case = 2
step = 3
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    agents = root / "resources" / "agents"
    _unit(agents, "01-alpha", "alpha")
    _unit(agents, "02-beta", "beta")
    registry = root / "resources" / "registry.toml"
    registry.write_text(REGISTRY, encoding="utf-8")
    load_registry(registry)
    return root, agents, registry


def _delete(project, target, *extra):
    _, agents, registry = project
    return cli(["agent", "delete", target, "--agents-dir", str(agents),
                "--registry", str(registry), *extra])


def _ids(registry: Path) -> list[str]:
    return [entry["agent_id"] for entry in tomllib.loads(registry.read_text(encoding="utf-8"))["agents"]]


@pytest.mark.parametrize("target", ["alpha", "01-alpha"])
def test_registered_agent_is_unregistered_and_archived(project, target, capsys):
    root, agents, registry = project
    assert _delete(project, target, "-y") == 0

    assert not (agents / "01-alpha").exists()
    archived = list((root / "cache" / "agent-trash").glob("*/01-alpha"))
    assert len(archived) == 1
    assert (archived[0] / "ground_truth" / ".gitkeep").is_file()
    assert _ids(registry) == ["beta"]
    beta = REGISTRY[REGISTRY.index('[[agents]]\nagent_id = "beta"'):]
    assert registry.read_text(encoding="utf-8").endswith(beta)
    assert load_registry(registry).find("beta", enabled_only=False).max_steps == 3
    out = capsys.readouterr().out
    assert "Removed alpha from the registry." in out
    assert str(archived[0]) in out


def test_last_entry_removal_keeps_a_valid_registry(project):
    _, agents, registry = project
    assert _delete(project, "beta", "-y") == 0
    assert _ids(registry) == ["alpha"]
    assert registry.read_text(encoding="utf-8").endswith("case = 1\n")
    assert (agents / "01-alpha").is_dir()


def test_dry_run_changes_nothing(project, capsys):
    root, agents, registry = project
    before = registry.read_bytes()
    assert _delete(project, "alpha", "--dry-run") == 0
    assert registry.read_bytes() == before
    assert (agents / "01-alpha").is_dir()
    assert not (root / "cache").exists()
    assert "Agent: alpha" in capsys.readouterr().out


def test_declined_prompt_changes_nothing(project, monkeypatch, capsys):
    root, agents, registry = project
    before = registry.read_bytes()
    monkeypatch.setattr(builtins, "input", lambda prompt: "n")
    assert _delete(project, "alpha") == 0
    assert registry.read_bytes() == before
    assert (agents / "01-alpha").is_dir()
    assert not (root / "cache").exists()
    assert "Cancelled; nothing was changed." in capsys.readouterr().out


def test_unregistered_folder_is_archived_without_touching_registry(project):
    root, agents, registry = project
    (agents / "03-imported" / "agent").mkdir(parents=True)
    before = registry.read_bytes()
    assert _delete(project, "03-imported", "-y") == 0
    assert not (agents / "03-imported").exists()
    assert list((root / "cache" / "agent-trash").glob("*/03-imported/agent"))
    assert registry.read_bytes() == before


def test_entry_whose_folder_is_missing_is_unregistered(project):
    root, agents, registry = project
    shutil.rmtree(agents / "01-alpha")
    assert _delete(project, "alpha", "-y") == 0
    assert _ids(registry) == ["beta"]
    assert not (root / "cache").exists()


@pytest.mark.parametrize("target", ["missing", "..", "../agents", "01-alpha/ground_truth"])
def test_unknown_or_path_like_targets_are_rejected(project, target, capsys):
    root, agents, registry = project
    before = registry.read_bytes()
    assert _delete(project, target, "-y") == 2
    assert "Agent delete error:" in capsys.readouterr().err
    assert registry.read_bytes() == before
    assert (agents / "01-alpha" / "ground_truth").is_dir()
    assert not (root / "cache").exists()


def test_folder_outside_agents_directory_is_refused(project, tmp_path, capsys):
    root, agents, registry = project
    other = tmp_path / "elsewhere"
    other.mkdir()
    before = registry.read_bytes()
    assert cli(["agent", "delete", "alpha", "--agents-dir", str(other),
                "--registry", str(registry), "-y"]) == 2
    assert "pass the matching --agents-dir" in capsys.readouterr().err
    assert registry.read_bytes() == before
    assert (agents / "01-alpha").is_dir()


def test_failed_registry_update_moves_folder_back(project, monkeypatch, capsys):
    root, agents, registry = project
    before = registry.read_bytes()

    def fail(self, target):
        raise OSError("simulated registry replace failure")

    monkeypatch.setattr(Path, "replace", fail)
    assert _delete(project, "alpha", "-y") == 2
    assert "simulated registry replace failure" in capsys.readouterr().err
    assert (agents / "01-alpha" / "agent.toml").is_file()
    assert registry.read_bytes() == before
    assert not list((root / "cache" / "agent-trash").glob("*/*"))
    assert not list(registry.parent.glob(".registry-delete-*"))


def test_agent_help_lists_add_and_delete(capsys):
    with pytest.raises(SystemExit):
        cli(["agent", "--help"])
    out = capsys.readouterr().out
    assert "add" in out and "delete" in out
