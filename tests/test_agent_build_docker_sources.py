"""Generated images must not COPY files that the workflow never created."""
from types import SimpleNamespace
import pytest
from tests.agent_build_fixtures import source, write, DOCKERFILE, MANIFEST
from agentbench.onboarding.build_agent_env.build_dockerfile.service import validate
from agentbench.onboarding.build_agent_env.common.errors import BuildError


@pytest.mark.parametrize("instruction", ["COPY bindings/ ./bindings/", 'COPY ["bindings/", "./bindings/"]'])
def test_missing_binding_directory_is_rejected_before_docker_build(source, instruction):
    write(source.directory, "agent.toml", MANIFEST)
    with pytest.raises(BuildError, match="bindings"):
        validate(DOCKERFILE + instruction + "\n", SimpleNamespace(source=source))


def test_real_bindings_and_injected_runtime_are_accepted(source):
    write(source.directory, "agent.toml", MANIFEST)
    write(source.directory, "bindings/bridge.py", "def create_graph(): pass")
    validate(DOCKERFILE + "COPY bindings/ ./bindings/\n", SimpleNamespace(source=source))
