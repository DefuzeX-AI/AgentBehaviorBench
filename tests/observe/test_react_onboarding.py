"""Initial ReAct manifest and isolated upstream graph validation."""
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / 'resources/agents/02-react-agent'


def test_react_configuration():
    from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
    from agentbench.runtime.interception import InterceptionConfig
    from agentbench.harness.registry import load_registry
    config = LangGraphAdapterConfig.from_agent_dir(AGENT)
    assert config.context == {'model': 'openai/gpt-4.1-mini', 'max_search_results': 5}
    assert config.binding == 'react.py:create_graph'
    assert config.input_key == 'message' and config.output_key == 'answer'
    interception = InterceptionConfig.from_agent_dir(AGENT)
    assert interception.routes[0].host_patterns == ('api.openai.com',)
    assert interception.tool_routes[0].host_patterns == ('api.tavily.com',)
    assert load_registry(ROOT / 'resources/registry.toml').find('react-agent').path == AGENT


@pytest.mark.skipif(os.getenv('ABB_DOCKER_TEST') != '1', reason='Opt-in offline ReAct Docker test')
def test_real_react_graph_worker_and_case_local_history():
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    from agentbench.runtime.docker.worker_build import worker_build_context
    from agentbench.runtime.docker.image_builder import DockerImageBuilder
    from agentbench.runtime.docker import DockerPolicy
    config = AgentContainerConfig.from_agent_dir(AGENT, secret_resolver=EnvironmentSecretResolver({'TAVILY_API_KEY':'offline-placeholder'}))
    with worker_build_context(config) as (context, dockerfile):
        image = DockerImageBuilder().build(context=context,dockerfile=dockerfile,repository='react-agent')
    script = Path(__file__).with_name('react_offline_checks.py')
    result = subprocess.run(['docker','run','--rm','--network','none', *DockerPolicy().run_arguments(),
        '--mount',f'type=bind,source={AGENT / "evaluation/input-contract.json"},target=/opt/agent/evaluation/input-contract.json,readonly',
        '--mount',f'type=bind,source={script},target=/checks.py,readonly',image,'python','/checks.py'],
        capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "passed"' in result.stdout
