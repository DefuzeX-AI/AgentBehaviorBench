"""Load and query the AgentBench resource registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


EXPECTED_SCHEMA_VERSION = "defuzex-bench.registry.v1"


@dataclass(frozen=True)
class AgentRegistration:
    agent_id: str
    path: Path
    enabled: bool
    status: str
    framework: str
    source: str
    case_count: int = 1
    requirement_path: Path | None = None


class AgentRegistry:
    def __init__(self, agents: list[AgentRegistration]) -> None:
        """Store agents by agent id."""
        self._agents = {agent.agent_id: agent for agent in agents}
        if len(self._agents) != len(agents):
            raise ValueError("Registry contains duplicate agent_id values")

    def find(self, agent_id: str, *, enabled_only: bool = True) -> AgentRegistration:
        """Find one agent by id."""
        try:
            agent = self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Agent is not registered: {agent_id}") from exc

        if enabled_only and not agent.enabled:
            raise ValueError(f"Agent is disabled: {agent_id}")
        return agent

    def enabled(self) -> tuple[AgentRegistration, ...]:
        """Return enabled agents only."""
        return tuple(agent for agent in self._agents.values() if agent.enabled)

    def enabled_with_status(self, status: str) -> tuple[AgentRegistration, ...]:
        """Return enabled agents with one registry lifecycle status."""
        return tuple(
            agent
            for agent in self._agents.values()
            if agent.enabled and agent.status == status
        )

    def ready(self) -> tuple[AgentRegistration, ...]:
        """Return enabled agents certified for default benchmark runs."""
        return self.enabled_with_status("ready")


def load_registry(registry_path: str | Path) -> AgentRegistry:
    """Read agent list from resources/registry.toml."""
    registry_file = Path(registry_path).resolve()
    with registry_file.open("rb") as stream:
        data = tomllib.load(stream)

    schema_version = data.get("schema_version")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise ValueError(f"Unsupported registry schema: {schema_version!r}")

    repo_root = registry_file.parent.parent
    agents = [_parse_agent(item, repo_root) for item in data.get("agents", [])]
    return AgentRegistry(agents)


def _parse_agent(item: dict[str, object], repo_root: Path) -> AgentRegistration:
    """Build one agent record from registry data."""
    agent_id = _required_string(item, "agent_id")
    relative_path = Path(_required_string(item, "path"))
    agent_path = (repo_root / relative_path).resolve()

    if not agent_path.is_relative_to(repo_root):
        raise ValueError(f"Agent path escapes repository: {relative_path}")
    if not agent_path.is_dir():
        raise FileNotFoundError(f"Agent directory does not exist: {agent_path}")

    manifest_path = agent_path / "agent.toml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Agent manifest does not exist: {manifest_path}")

    with manifest_path.open("rb") as stream:
        manifest = tomllib.load(stream)
    if manifest.get("agent_id") != agent_id:
        raise ValueError(f"Registry and manifest agent_id differ for {agent_id}")

    source_path = (agent_path / "agent").resolve()
    if not source_path.is_relative_to(agent_path):
        raise ValueError(f"Agent source escapes agent directory: {source_path}")
    if not source_path.is_dir():
        raise FileNotFoundError(f"Agent source directory does not exist: {source_path}")

    from agentbench.runtime.agentcontainer.config import manifest_runtime_type, docker_structure
    if manifest_runtime_type(manifest) == "docker":
        docker_structure(agent_path, manifest)

    requirement_path = (agent_path / "requirement.md").resolve()
    if not requirement_path.is_relative_to(agent_path):
        raise ValueError(f"Agent requirement escapes agent directory: {requirement_path}")
    if not requirement_path.is_file():
        raise FileNotFoundError(
            f"Agent requirement does not exist: {requirement_path}"
        )

    return AgentRegistration(
        agent_id=agent_id,
        path=agent_path,
        enabled=bool(item.get("enabled", True)),
        status=str(item.get("status", "unknown")),
        framework=_required_string(item, "framework"),
        source=str(item.get("source", "")),
        case_count=_positive_integer(item, "case", default=1),
        requirement_path=requirement_path,
    )


def _required_string(item: dict[str, object], key: str) -> str:
    """Read a required string field."""
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Registry field must be a non-empty string: {key}")
    return value


def _positive_integer(
    item: dict[str, object], key: str, *, default: int
) -> int:
    """Read an optional positive integer field."""

    value = item.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Registry field must be a positive integer: {key}")
    return value
