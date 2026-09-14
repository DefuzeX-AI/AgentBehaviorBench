"""Issue #31: callbacks are created only in the process running the Agent."""
from types import SimpleNamespace

from agentbench.observe.host import host_observation_factory


def test_docker_agent_never_gets_host_callback(tmp_path):
    agent_root = tmp_path / 'agent'
    agent_root.mkdir()
    (agent_root / 'agent.toml').write_text('[runtime]\ntype="docker"\n')
    factory = host_observation_factory(tmp_path / 'artifacts')
    observed = factory(SimpleNamespace(path=agent_root, agent_id='agent', framework='langgraph'),
                       SimpleNamespace(run_id='sdk-run'))
    assert observed is None
    assert not (tmp_path / 'artifacts').exists()
