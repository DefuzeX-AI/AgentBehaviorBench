from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("agent_id", "directory", "enabled", "status", "case_count"),
    [
        (
            "company-research-agent",
            "01-company-research-agent",
            True,
            "adapting",
            1,
        ),
    ],
)
def test_registry_resolves_registered_agents(
    agent_id: str, directory: str, enabled: bool, status: str, case_count: int
) -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

    agent = registry.find(agent_id, enabled_only=False)

    assert agent.agent_id == agent_id
    assert agent.enabled is enabled
    assert agent.framework == "langgraph"
    assert agent.status == status
    assert agent.case_count == case_count
    assert agent.path == REPO_ROOT / "resources" / "agents" / directory
    assert agent.path.joinpath("agent.toml").is_file()
    assert agent.requirement_path == agent.path / "requirement.md"
    assert (agent.path / "agent").is_dir()
    assert (agent.path / "Dockerfile").is_file()


def test_every_enabled_agent_has_an_sdk_requirement() -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

    for agent in registry.enabled():
        requirement = agent.path / "requirement.md"
        assert requirement.is_file(), f"Missing SDK requirement: {requirement}"
        assert agent.requirement_path == requirement


def test_ready_agents_are_the_default_runnable_subset() -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

    assert registry.ready() == ()
    assert {agent.agent_id for agent in registry.enabled()} == {"company-research-agent"}
    assert {path.name for path in (REPO_ROOT / "resources" / "agents").iterdir() if path.is_dir()} == {
        "01-company-research-agent",
    }
    assert {agent.agent_id for agent in registry.enabled_with_status("adapting")} == {
        "company-research-agent",
    }


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
