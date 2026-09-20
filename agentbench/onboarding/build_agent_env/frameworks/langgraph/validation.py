"""Validate LangGraph source facts and outer bindings, without imports."""
import re
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from ...common.errors import BuildError
from ...common.paths import file_path
from ...openrouter_provider.context import safe_file
from .binding_validation import validate_binding


def validate_manifest(manifest, session):
    adapter = manifest["adapter"]
    binding = adapter.get("binding")
    if not isinstance(binding, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.py:[A-Za-z_][A-Za-z0-9_]*", binding):
        raise BuildError("Onboarding requires adapter.binding='filename.py:factory' relative to outer bindings/; "
                         "the selected synchronous factory must be callable without arguments")
    config_name = adapter.get("config", "")
    source = session.source.directory / "agent"
    config_path = safe_file(source, config_name) if isinstance(config_name, str) else None
    if config_path is None:
        raise BuildError("adapter.config must reference an existing file inside agent/")
    # The temporary unit holds only manifest and graph descriptor.
    return config_name, config_path


def validate_selection(parsed, session):
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


def validate_unit(root, manifest, session):
    adapter = LangGraphAdapterConfig.from_agent_dir(root)
    filename, _, attribute = (adapter.binding or adapter.entrypoint).rpartition(":")
    entry_root = root / "bindings" if adapter.binding else root / "agent"
    if not attribute or safe_file(entry_root, filename) is None:
        raise BuildError("Adapter entrypoint does not reference an existing local file")
    session.completed = {"agent.toml": (root / "agent.toml").read_text()}
    session.current_path = "bindings/" + filename
    validate_binding((entry_root / filename).read_text(), session)
