"""Check all installed files together before registering or certifying a unit."""
from types import SimpleNamespace

from agentbench.runtime.agentcontainer.config import AgentContainerConfig, tomllib
from agentbench.sdk.contracts import SDKOnboardingContext
from ..build_toml.frameworks import config_reader
from ..build_toml.validation import _PlaceholderSecrets, validate_manifest
from ..build_blinding.validation import validate_binding
from ..build_dockerfile.service import validate as validate_dockerfile
from ..openrouter_provider.context import safe_file
from .errors import BuildError
from .paths import REQUIRED_FILES


def validate_unit(root, sdk, *, expected_id=None, sdk_context=None):
    for name in REQUIRED_FILES:
        if safe_file(root, name) is None:
            raise BuildError(f"Missing or unsafe integration file: {name}")
    session = SimpleNamespace(source=SimpleNamespace(directory=root), agent_id=expected_id,
                              plan={"bindings": []})
    validate_manifest((root / "agent.toml").read_text(), session)
    manifest = tomllib.loads((root / "agent.toml").read_text())
    adapter = config_reader(manifest.get("framework"))(root)
    filename, _, attribute = (adapter.binding or adapter.entrypoint).rpartition(":")
    entry_root = root / "bindings" if adapter.binding else root / "agent"
    if not attribute or safe_file(entry_root, filename) is None:
        raise BuildError("Adapter entrypoint does not reference an existing local file")
    session.completed = {"agent.toml": (root / "agent.toml").read_text()}
    session.current_path = "bindings/" + filename
    validate_binding((entry_root / filename).read_text(), session)
    container = AgentContainerConfig.from_agent_dir(root, secret_resolver=_PlaceholderSecrets(), environ={})
    validate_dockerfile(container.dockerfile.read_text(), session)
    sdk.validate_onboarding(root)
    if sdk_context is not None and isinstance(sdk, SDKOnboardingContext):
        sdk.validate_onboarding_context(root, context=sdk_context)
    return container.agent_id
