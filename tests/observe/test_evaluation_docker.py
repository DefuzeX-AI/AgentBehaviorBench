import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import pytest
from agentbench.sdk.kuma.image import evaluation_agent
from agentbench.sdk.kuma.service import EvaluationPolicy
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.docker.worker_build import worker_build_context
from agentbench.runtime.docker.image_builder import DockerImageBuilder


@pytest.mark.skipif(os.getenv('ABB_DOCKER_TEST') != '1', reason='Opt-in real offline Docker')
def test_company_sdk_execute_in_same_container(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    agent = SimpleNamespace(path=repo / 'resources/agents/01-company-research-agent',
                            agent_id='company-research-agent', framework='langgraph')
    with evaluation_agent(agent, repo.parent / 'Defuze-SDK') as staged:
        config = AgentContainerConfig.from_agent_dir(staged.path,
            secret_resolver=EnvironmentSecretResolver({'TAVILY_API_KEY': 'offline'}))
        with worker_build_context(config) as (context, dockerfile):
            image = DockerImageBuilder().build(context=context, dockerfile=dockerfile, repository='company-sdk-test')
        repository = tmp_path / 'repository'
        shutil.copytree(staged.path / 'agent', repository)
        state = repository / '.kuma'; state.mkdir(); state.chmod(0o777)
        fixtures = tmp_path / 'fixtures'; fixtures.mkdir()
        shutil.copy(repo / 'tests/acceptance/company_sdk/verify_execution.py', fixtures / 'check.py')
        shutil.copy(repo / 'tests/observe/company_upstream.py', fixtures)
        shutil.copytree(repo / 'agentbench/services/model-interceptor/src/defuzex_model_interceptor', fixtures / 'defuzex_model_interceptor')
        output = tmp_path / 'output'; output.mkdir(); output.chmod(0o777)
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
            *EvaluationPolicy(state).run_arguments(),
            '--mount', f'type=bind,source={fixtures},target=/run/checks,readonly',
            '--mount', f'type=bind,source={output},target=/run/abb-output',
            '--env', 'OPENAI_API_KEY=offline', '--env', 'GEMINI_API_KEY=offline', '--env', 'TAVILY_API_KEY=offline',
            image, 'python', '/run/checks/check.py'], capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
