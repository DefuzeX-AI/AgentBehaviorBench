"""New adapting registrations stay out of default run/evaluate selection."""

from pathlib import Path

from agentbench.harness.registry import load_registry, tomllib
from agentbench.onboarding.build_agent_env.common.registry import register_agent


MANIFEST = """schema_version = "defuzex-bench.agent.v2"
agent_id = "fixture-adapting-agent"
framework = "langgraph"
"""


def test_register_agent_starts_adapting_units_disabled(tmp_path):
    root = tmp_path / "project"
    unit = root / "resources" / "agents" / "01-fixture"
    unit.mkdir(parents=True)
    (unit / "agent.toml").write_text(MANIFEST, encoding="utf-8")
    (unit / "requirement.md").write_text("fixture requirement\n", encoding="utf-8")
    (unit / "agent").mkdir()
    registry = root / "resources" / "registry.toml"
    registry.write_text('schema_version = "defuzex-bench.registry.v1"\n', encoding="utf-8")

    assert register_agent(unit, registry, "https://github.com/example/fixture") == (
        "fixture-adapting-agent"
    )

    entry = tomllib.loads(registry.read_text(encoding="utf-8"))["agents"][0]
    assert entry["agent_id"] == "fixture-adapting-agent"
    assert entry["status"] == "adapting"
    assert entry["enabled"] is False
    agent = load_registry(registry).find("fixture-adapting-agent", enabled_only=False)
    assert agent.enabled is False
    assert agent.status == "adapting"


def test_bundled_adapting_agents_are_disabled():
    root = Path(__file__).resolve().parents[1]
    registry_path = root / "resources" / "registry.toml"
    if not registry_path.is_file():
        return
    with registry_path.open("rb") as stream:
        entries = tomllib.load(stream)["agents"]
    enabled_adapting = [
        entry["agent_id"]
        for entry in entries
        if entry.get("status") == "adapting" and entry.get("enabled", True)
    ]
    assert enabled_adapting == [], (
        "adapting Agents must stay disabled until certification: "
        + ", ".join(enabled_adapting)
    )
