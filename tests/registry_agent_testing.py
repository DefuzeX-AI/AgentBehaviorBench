"""Tests for registry discovery at the start of the ``agentbench run`` command."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path

import pytest

from agentbench.cli.configuration import RunConfiguration


@pytest.fixture
def run_feature(monkeypatch):
    """Import the command module and remove presentation delays."""

    feature = importlib.import_module("agentbench.cli.features.run")
    monkeypatch.setattr(feature, "print_logo", lambda _: None)
    monkeypatch.setattr(feature.time, "sleep", lambda _: None)
    return feature


def write_registry(
    tmp_path: Path,
    agents: tuple[tuple[str, str], ...] = (("ready-agent", "ready"),),
    *,
    schema_version: str = "defuzex-bench.registry.v1",
) -> tuple[Path, dict[str, Path]]:
    """Create a small, valid registry and its Agent filesystem entries."""

    registry_path = tmp_path / "resources" / "registry.toml"
    registry_path.parent.mkdir()
    records = [f'schema_version = "{schema_version}"', ""]
    agent_paths: dict[str, Path] = {}

    for agent_id, status in agents:
        agent_path = registry_path.parent / "agents" / agent_id
        agent_path.mkdir(parents=True)
        (agent_path / "agent").mkdir()
        (agent_path / "agent.toml").write_text(
            f'agent_id = "{agent_id}"\n', encoding="utf-8"
        )
        (agent_path / "requirement.md").write_text("fixture requirement\n", encoding="utf-8")
        records.extend(
            [
                "[[agents]]",
                f'agent_id = "{agent_id}"',
                f'path = "resources/agents/{agent_id}"',
                "enabled = true",
                f'status = "{status}"',
                'framework = "langgraph"',
                'source = "test fixture"',
                "",
            ]
        )
        agent_paths[agent_id] = agent_path

    registry_path.write_text("\n".join(records), encoding="utf-8")
    return registry_path, agent_paths


def test_run_loads_ready_agents_and_reports_excluded_adapting_agents(
    tmp_path: Path, monkeypatch, run_feature
) -> None:
    registry_path, _ = write_registry(
        tmp_path,
        (("ready-agent", "ready"), ("needs-certification", "adapting")),
    )
    monkeypatch.setattr(run_feature, "DEFAULT_REGISTRY_PATH", registry_path)
    confirmed: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        run_feature,
        "confirm_agents",
        lambda agents, **_: confirmed.append(tuple(agent.agent_id for agent in agents)) or False,
    )
    messages: list[str] = []

    exit_code = run_feature.run(RunConfiguration(output_fn=messages.append))

    assert exit_code == 0
    assert confirmed == [("ready-agent",)]
    assert messages == [
        "1 adapting Agent excluded from this run. "
        "Use 'agentbench certify <agent_id>' when an adapter is ready."
    ]


def test_run_returns_one_and_never_prompts_when_registry_has_no_ready_agents(
    tmp_path: Path, monkeypatch, run_feature
) -> None:
    registry_path, _ = write_registry(tmp_path, (("needs-certification", "adapting"),))
    monkeypatch.setattr(run_feature, "DEFAULT_REGISTRY_PATH", registry_path)
    displayed: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        run_feature, "print_agents", lambda agents, _: displayed.append(agents)
    )
    monkeypatch.setattr(
        run_feature,
        "confirm_agents",
        lambda *_args, **_kwargs: pytest.fail("an empty ready set must not prompt"),
    )
    messages: list[str] = []

    exit_code = run_feature.run(RunConfiguration(output_fn=messages.append))

    assert exit_code == 1
    assert displayed == [()]
    assert messages == ["No enabled ready benchmark agents detected."]


def test_run_surfaces_a_missing_registry_file_with_its_path(
    tmp_path: Path, monkeypatch, run_feature
) -> None:
    missing_registry = tmp_path / "resources" / "registry.toml"
    monkeypatch.setattr(run_feature, "DEFAULT_REGISTRY_PATH", missing_registry)

    with pytest.raises(FileNotFoundError, match="registry\\.toml") as error:
        run_feature.run(RunConfiguration())

    assert Path(error.value.filename) == missing_registry.resolve()


@pytest.mark.parametrize(
    ("missing_name", "expected_message"),
    [
        ("agent.toml", "Agent manifest does not exist"),
        ("agent", "Agent source directory does not exist"),
        ("requirement.md", "Agent requirement does not exist"),
    ],
)
def test_run_reports_missing_required_agent_files(
    tmp_path: Path,
    monkeypatch,
    run_feature,
    missing_name: str,
    expected_message: str,
) -> None:
    registry_path, agents = write_registry(tmp_path)
    missing_path = agents["ready-agent"] / missing_name
    if missing_path.is_dir():
        missing_path.rmdir()
    else:
        missing_path.unlink()
    monkeypatch.setattr(run_feature, "DEFAULT_REGISTRY_PATH", registry_path)

    with pytest.raises(FileNotFoundError, match=expected_message) as error:
        run_feature.run(RunConfiguration())

    assert str(missing_path.resolve()) in str(error.value)


def test_run_surfaces_an_unsupported_registry_schema(
    tmp_path: Path, monkeypatch, run_feature
) -> None:
    registry_path, _ = write_registry(tmp_path, schema_version="old-schema")
    monkeypatch.setattr(run_feature, "DEFAULT_REGISTRY_PATH", registry_path)

    with pytest.raises(ValueError, match="Unsupported registry schema: 'old-schema'"):
        run_feature.run(RunConfiguration())


@pytest.mark.parametrize(
    ("configuration", "message"),
    [
        (
            RunConfiguration(sdk=object(), sdk_selection=object()),
            "Pass sdk or sdk_selection, not both",
        ),
        (
            RunConfiguration(suite_runner=object(), sdk=object()),
            "Configure sdk on the supplied suite_runner, or omit suite_runner",
        ),
    ],
)
def test_run_rejects_conflicting_configuration_before_registry_access(
    run_feature, configuration: RunConfiguration, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_feature.run(configuration)
