from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_registry_resolves_registered_agents():
    from agentbench.runtime.agentcontainer.config import tomllib
    registry = load_registry(REPO_ROOT / 'resources/registry.toml')
    data = tomllib.loads((REPO_ROOT / 'resources/registry.toml').read_text())
    for entry in data['agents']:
        agent = registry.find(entry['agent_id'], enabled_only=False)
        assert agent.path == (REPO_ROOT / entry['path']).resolve()
        assert agent.status == entry['status']
        assert (agent.path / 'agent').is_dir()
        assert agent.requirement_path.is_file()


def test_every_enabled_agent_has_an_sdk_requirement() -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

    for agent in registry.enabled():
        requirement = agent.path / "requirement.md"
        assert requirement.is_file(), f"Missing SDK requirement: {requirement}"
        assert agent.requirement_path == requirement


def test_ready_agents_are_the_default_runnable_subset(tmp_path):
    from dataclasses import replace
    from agentbench.harness.registry import AgentRegistry
    agent = load_registry(_write_registry(tmp_path)).find('test-agent')
    records = [replace(agent, agent_id=f'fixture-{i}', status=status, enabled=enabled)
               for i, (status, enabled) in enumerate([
                   ('ready', True), ('ready', False), ('adapting', True), ('blocked', True)])]
    registry = AgentRegistry(records)
    assert registry.ready() == (records[0],)
    assert registry.enabled_with_status('adapting') == (records[2],)


def test_registered_units_have_matching_manifest_identity():
    # Downloaded but unregistered units may coexist with the benchmark registry.
    registry = load_registry(REPO_ROOT / 'resources/registry.toml')
    from agentbench.runtime.agentcontainer.config import tomllib
    data = tomllib.loads((REPO_ROOT / 'resources/registry.toml').read_text())
    for entry in data['agents']:
        agent = registry.find(entry['agent_id'], enabled_only=False)
        manifest = tomllib.loads((agent.path / 'agent.toml').read_text())
        assert manifest['agent_id'] == agent.agent_id


def test_registry_defaults_case_count_to_one(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)

    agent = load_registry(registry_path).find("test-agent")

    assert agent.case_count == 1


@pytest.mark.parametrize("case_value", ["0", "-1", "true", '"2"', "1.5"])
def test_registry_rejects_invalid_case_count(
    tmp_path: Path, case_value: str
) -> None:
    registry_path = _write_registry(tmp_path, case_value=case_value)

    with pytest.raises(ValueError, match="positive integer: case"):
        load_registry(registry_path)


def test_registry_uses_user_named_directory(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path, directory="01-my-research")
    agent = load_registry(registry_path).find("test-agent")
    assert agent.path.name == "01-my-research"
    assert agent.requirement_path == agent.path / "requirement.md"


def test_registry_does_not_fall_back_to_global_requirement(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    (tmp_path / "resources/agents/test-agent/requirement.md").unlink()
    legacy = tmp_path / "resources/requirements/test-agent.md"
    legacy.parent.mkdir()
    legacy.write_text("Legacy requirement", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="requirement.md"):
        load_registry(registry_path)


@pytest.mark.parametrize("missing", ["agent", "Dockerfile"])
def test_registry_rejects_incomplete_unit(tmp_path: Path, missing: str) -> None:
    registry_path = _write_registry(tmp_path)
    if missing == "Dockerfile":
        manifest = tmp_path / "resources/agents/test-agent/agent.toml"
        manifest.write_text(manifest.read_text() + '\n[runtime]\ntype="docker"\n[build]\ncontext="."\ndockerfile="Dockerfile"\n[launch]\nargv=["python"]\n')
    path = tmp_path / "resources/agents/test-agent" / missing
    if path.is_dir():
        path.rmdir()
    else:
        path.unlink()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load_registry(registry_path)


def _write_registry(
    tmp_path: Path, *, case_value: str | None = None, directory: str = "test-agent"
) -> Path:
    resources = tmp_path / "resources"
    agent_path = resources / "agents" / directory
    requirement_path = agent_path / "requirement.md"
    agent_path.mkdir(parents=True)
    (agent_path / "agent").mkdir()
    (agent_path / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    (agent_path / "agent.toml").write_text(
        'agent_id = "test-agent"\n', encoding="utf-8"
    )
    requirement_path.write_text("# Test requirement\n", encoding="utf-8")
    case_line = "" if case_value is None else f"case = {case_value}\n"
    registry_path = resources / "registry.toml"
    registry_path.write_text(
        'schema_version = "defuzex-bench.registry.v1"\n\n'
        "[[agents]]\n"
        'agent_id = "test-agent"\n'
        f'path = "resources/agents/{directory}"\n'
        'framework = "langgraph"\n'
        f"{case_line}",
        encoding="utf-8",
    )
    return registry_path
