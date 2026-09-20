"""Validate a manifest before Dockerfile and required bindings exist."""

import re
import tempfile
from pathlib import Path

from .frameworks import config_reader
from ..frameworks.registry import strategy
from .environment import CREDENTIAL_NAME
from agentbench.runtime.agentcontainer.config import AgentContainerConfig, execution_strategy, tomllib
from agentbench.runtime.interception.config import InterceptionConfig
from ..common.errors import BuildError


class _PlaceholderSecrets:
    def require(self, name):
        return "validation-placeholder"


def validate_manifest(content, session):
    """Check one TOML file against actual source and planned later outputs.

    A temporary minimal unit lets the existing configuration readers validate
    their own fields. Placeholder Dockerfile content is never built or executed.
    """
    manifest = tomllib.loads(content)
    agent_id = manifest.get("agent_id", "")
    if not isinstance(agent_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", agent_id):
        raise BuildError("agent_id must contain lowercase letters, digits and hyphens")
    if session.agent_id and agent_id != session.agent_id:
        raise BuildError("Generated agent_id differs from the requested unit")
    if manifest.get("schema_version") != "defuzex-bench.agent.v2":
        raise BuildError("Expected a v2 Agent manifest")
    read_config = config_reader(manifest.get("framework"))
    adapter = manifest.get("adapter")
    if not isinstance(adapter, dict):
        raise BuildError("agent.toml needs an [adapter] table")
    selected = strategy(manifest.get("framework"))
    config_name, config_path = selected.validate_manifest(manifest, session)
    build = manifest.get("build", {})
    if not isinstance(build, dict) or build.get("context") != "." or build.get("dockerfile") != "Dockerfile":
        raise BuildError("Use build.context='.' and build.dockerfile='Dockerfile'")
    with tempfile.TemporaryDirectory(prefix="agent-manifest-check-") as directory:
        root = Path(directory)
        (root / "agent.toml").write_text(content)
        selected.stage_validation(root, config_name, config_path)
        (root / "Dockerfile").write_text("FROM scratch\n")
        parsed = read_config(root)
        AgentContainerConfig.from_agent_dir(root, secret_resolver=_PlaceholderSecrets(), environ={})
        execution_strategy(root)
        interception = InterceptionConfig.from_agent_dir(root)
    selected.validate_selection(parsed, session)
    validate_credentials(manifest.get("runtime", {}), interception)


def validate_credentials(runtime, interception):
    problems = []
    names = [key for key in runtime.get("env_keys", [])
             if CREDENTIAL_NAME.search(key)]
    if names:
        problems.append("Remove credentials from env_keys: " + ", ".join(names) +
                        "; tool credentials belong only in secret_env_keys")
    if interception:
        copied = set(runtime.get("secret_env_keys", [])).intersection(
            credential.agent_env for credential in interception.credentials)
        if copied:
            problems.append("Remove intercepted model credentials from secret_env_keys: " + ", ".join(sorted(copied)))
        if runtime.get("secret_env_keys") and not interception.tool_routes:
            problems.append("Declare actual tool_routes for tool credentials, or return needs_input for unknown endpoints")
    if problems:
        raise BuildError("; ".join(problems))
