"""Check all installed files together before registering or certifying a unit."""
from types import SimpleNamespace

from agentbench.runtime.agentcontainer.config import AgentContainerConfig, tomllib
from agentbench.sdk.contracts import SDKOnboardingContext
from ..frameworks.registry import strategy
from ..build_toml.validation import _PlaceholderSecrets, validate_manifest
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
    strategy(manifest.get("framework")).validate_unit(root, manifest, session)
    container = AgentContainerConfig.from_agent_dir(root, secret_resolver=_PlaceholderSecrets(), environ={})
    validate_dockerfile(container.dockerfile.read_text(), session)
    sdk.validate_onboarding(root)
    if sdk_context is not None and isinstance(sdk, SDKOnboardingContext):
        sdk.validate_onboarding_context(root, context=sdk_context)
    return container.agent_id
