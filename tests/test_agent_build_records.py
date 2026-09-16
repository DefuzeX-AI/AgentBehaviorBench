"""Generated artifacts and resumable logs have separate destinations."""
from tests.agent_build_fixtures import source, plan, build, Client
from agentbench.harness.registry import load_registry


def test_records_outside_unit_and_resume_keeps_registration(source, plan):
    result = build(source, plan)
    repo = source.directory.parents[2]
    assert result.attempt.is_relative_to(repo / "cache/onboarding")
    assert not (source.directory / "onboarding").exists()
    assert (source.directory / "agent.toml").exists()
    assert not (source.directory / "agent/agent.toml").exists()
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert client.requests == []
    assert load_registry(repo / "resources/registry.toml").find("my-agent").status == "adapting"
