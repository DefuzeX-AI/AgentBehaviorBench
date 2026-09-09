"""Container contracts use a dedicated fixture, independent of the Agent catalog."""
from pathlib import Path

import pytest

from agentbench.adapter import DEFAULT_ADAPTER_FACTORY
from agentbench.adapter import AdapterInvocation
from agentbench.harness import AgentRegistration
from agentbench.runtime.agentcontainer import AgentContainerConfig, ContainerAgentAdapter
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.factory import RuntimeFactory
from agentbench.runtime.interception import InterceptionConfig
from agentbench.runtime.agentcontainer.config import runtime_type


def test_fixture_declares_manifest_v2_interception(repo_root: Path) -> None:
    config = InterceptionConfig.from_agent_dir(repo_root / "tests/fixtures/interceptor-agent")
    assert config is not None
    assert config.required
    assert config.routes


def test_container_configuration_is_machine_driven(repo_root: Path) -> None:
    config = AgentContainerConfig.from_agent_dir(
        repo_root / "tests/fixtures/interceptor-agent",
        secret_resolver=EnvironmentSecretResolver({}),
        environ={},
    )
    assert config.argv == ("python", "/opt/agent/worker.py")
    assert config.timeout_sec == 30
    assert config.environment == {}
    assert config.build_context == repo_root / "tests/fixtures/interceptor-agent"
    assert config.dockerfile == config.build_context / "Dockerfile"


def test_company_research_selects_docker_without_importing_source(registry) -> None:
    registration = registry.find("company-research-agent")
    assert runtime_type(registration.path) == "docker"
    adapter = RuntimeFactory().create_adapter(
        registration, adapter_factory=DEFAULT_ADAPTER_FACTORY
    )
    assert isinstance(adapter, ContainerAgentAdapter)
    assert not adapter.is_loaded


def test_runtime_factory_selects_container_without_starting_docker(repo_root: Path) -> None:
    class NeverStartedRuntime:
        def start(self, agent):
            raise AssertionError("Runtime should remain lazy")

    registration = AgentRegistration(
        agent_id="interceptor-smoke-agent",
        path=repo_root / "tests/fixtures/interceptor-agent",
        enabled=True,
        status="ready",
        framework="fixture",
        source="test-fixture",
    )
    factory = RuntimeFactory(docker_builder=NeverStartedRuntime)
    adapter = factory.create_adapter(registration, adapter_factory=DEFAULT_ADAPTER_FACTORY)
    assert isinstance(adapter, ContainerAgentAdapter)
    assert not adapter.is_loaded


def test_explicit_caller_works_with_lifecycle_only_session(starter_agent):
    events = []

    class Session:
        is_running = True

        def trace_checkpoint(self):
            events.append("checkpoint")
            return "checkpoint-1"

        def validate_trace(self, checkpoint):
            assert checkpoint == "checkpoint-1"
            events.append("validate")

        def close(self):
            self.is_running = False
            events.append("close")

    session = Session()

    class Runtime:
        def start(self, agent):
            events.append("start")
            return session

    def caller(running, value, config):
        assert running is session
        assert config == {"job": 1}
        events.append("native call")
        return AdapterInvocation(output=value, raw_output="native response")

    adapter = ContainerAgentAdapter(starter_agent, Runtime(), caller=caller)
    try:
        result = adapter.invoke("company", run_config={"job": 1})
        assert result.output == "company"
        assert result.raw_output == "native response"
    finally:
        adapter.close()
    assert events == ["start", "checkpoint", "native call", "validate", "close"]


def test_missing_caller_does_not_start_a_container(starter_agent):
    class Runtime:
        def start(self, agent):
            raise AssertionError("Missing API caller must fail before startup")

    adapter = ContainerAgentAdapter(starter_agent, Runtime())
    with pytest.raises(RuntimeError, match="No native Agent caller configured"):
        adapter.invoke("company")
