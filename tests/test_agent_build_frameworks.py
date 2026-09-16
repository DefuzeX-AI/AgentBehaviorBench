"""Infer framework separately from available runtime/onboarding capabilities."""

import pytest

from agentbench.adapter.factory import AdapterFactory
from agentbench.onboarding.build_agent_env.build_toml import frameworks
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, FILES, build


def test_requests_receive_current_framework_contracts(source, plan):
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    for request in client.requests:
        assert set(request["framework_requirements"]) == set(frameworks.supported_frameworks())
        assert 'type="langgraph"' in request["framework_requirements"]["langgraph"]


def test_unknown_framework_is_not_accepted_as_langgraph(source, plan):
    files = {**FILES, "agent.toml": FILES["agent.toml"].replace(
        'framework = "langgraph"', 'framework = "another-framework"')}
    with pytest.raises(BuildError, match="Unsupported onboarding framework 'another-framework'"):
        build(source, plan, client=Client(plan, files=files))
    assert not (source.directory / "agent.toml").exists()


def test_runtime_registration_alone_does_not_advertise_generation_support(monkeypatch):
    factory = AdapterFactory({"another-framework": lambda path: None})
    monkeypatch.setattr(frameworks, "DEFAULT_ADAPTER_FACTORY", factory)
    assert frameworks.framework_requirements() == {}
    with pytest.raises(BuildError, match="supported: none"):
        frameworks.config_reader("another-framework")


def test_new_framework_instructions_invalidate_cached_plan(source, plan, monkeypatch):
    build(source, plan)
    original = frameworks.framework_requirements
    from agentbench.onboarding.build_agent_env.common import checkpoint
    monkeypatch.setattr(checkpoint, "framework_requirements",
                        lambda: {**original(), "changed-contract": "new instructions"})
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert [request.get("target_path") for request in client.requests] == [None]
