"""Append one adapting registration while preserving existing registry content."""

import json
import tempfile
from pathlib import Path

from agentbench.harness.registry import EXPECTED_SCHEMA_VERSION, load_registry
from agentbench.harness.session.locking import SuiteLock
from agentbench.runtime.agentcontainer.config import tomllib

from .errors import BuildError
from .writer import confined


def register_agent(unit: Path, registry_path: Path, repository: str) -> str:
    """Return agent_id after validating and atomically registering one local unit.

    Existing entries must point at the same unit; their enabled/status/case values
    are preserved. The model never writes registry TOML or promotes an Agent.
    """
    path = registry_path.absolute()
    if path.is_symlink():
        raise BuildError("Registry path must not be a symlink")
    root = path.parent.parent.resolve()
    try:
        relative = unit.resolve().relative_to(root).as_posix()
    except ValueError:
        raise BuildError("Agent directory must be inside the --registry repository root") from None
    manifest = tomllib.loads((unit / "agent.toml").read_text())
    agent_id = manifest["agent_id"]
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = SuiteLock(confined(path.parent, ".agent-add-lock"))
    lock.acquire()
    try:
        original = path.read_text() if path.exists() else None
        text = original if original is not None else f'schema_version = "{EXPECTED_SCHEMA_VERSION}"\n'
        data = tomllib.loads(text)
        for entry in data.get("agents", []):
            same_id = entry.get("agent_id") == agent_id
            same_path = (root / entry.get("path", "")).resolve() == unit.resolve()
            if same_id != same_path:
                raise BuildError("Registry already contains this agent_id or directory with another identity")
            if same_id:
                load_registry(path)
                return agent_id
        entry = {"agent_id": agent_id, "path": relative, "enabled": True,
                 "status": "adapting", "framework": manifest["framework"],
                 "source": repository, "case": 1}
        block = "\n[[agents]]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in entry.items())
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".registry-add-", suffix=".toml", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text + block)
        try:
            load_registry(temporary)
            current = path.read_text() if path.exists() else None
            if current != original:
                raise BuildError("Registry changed during onboarding; retry without rebuilding")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return agent_id
    finally:
        lock.close()
