"""Validate a manifest before Dockerfile and required bindings exist."""

import re
import tempfile
from pathlib import Path

from .frameworks import config_reader
from .environment import CREDENTIAL_NAME
from agentbench.runtime.agentcontainer.config import AgentContainerConfig, execution_strategy, tomllib
from agentbench.runtime.interception.config import InterceptionConfig
from ..common.errors import BuildError
from ..common.paths import file_path
from ..openrouter_provider.context import safe_file


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
    binding = adapter.get("binding")
    if not isinstance(binding, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.py:[A-Za-z_][A-Za-z0-9_]*", binding):
        raise BuildError("Onboarding requires adapter.binding='filename.py:factory' relative to outer bindings/; "
                         "the selected synchronous factory must be callable without arguments")
    config_name = adapter.get("config", "")
    source = session.source.directory / "agent"
    config_path = safe_file(source, config_name) if isinstance(config_name, str) else None
    if config_path is None:
        raise BuildError("adapter.config must reference an existing file inside agent/")
    build = manifest.get("build", {})
    if not isinstance(build, dict) or build.get("context") != "." or build.get("dockerfile") != "Dockerfile":
        raise BuildError("Use build.context='.' and build.dockerfile='Dockerfile'")
    with tempfile.TemporaryDirectory(prefix="agent-manifest-check-") as directory:
        root = Path(directory)
        (root / "agent.toml").write_text(content)
        target = root / "agent" / config_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(config_path.read_text())
        (root / "Dockerfile").write_text("FROM scratch\n")
        parsed = read_config(root)
        AgentContainerConfig.from_agent_dir(root, secret_resolver=_PlaceholderSecrets(), environ={})
        execution_strategy(root)
        interception = InterceptionConfig.from_agent_dir(root)
    filename, separator, attribute = parsed.binding.rpartition(":")
    if not separator or not attribute:
        raise BuildError("The selected file-based adapter entrypoint must use file.py:attribute")
    name = "bindings/" + filename
    file_path(name)
    planned = session.plan.get("bindings", [])
    if planned and name not in planned:
        raise BuildError("Manifest binding must select a file in plan.bindings")
    if not planned and safe_file(session.source.directory, name) is None:
        raise BuildError("Manifest binding must reference a planned or existing binding file")
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
