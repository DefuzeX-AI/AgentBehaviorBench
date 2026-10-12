"""Issue #39: new Agent boundaries preserve real inputs and require certification."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.registered_agents import binding, unit as registered_unit, require_source
from agentbench.runtime.interception.config import InterceptionConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('unit', ['tradingagents', 'gpt-researcher'])
def test_new_agents_load_with_explicit_routes_without_input_contract(unit):
    import ast
    path = registered_unit(unit)
    from agentbench.harness.registry import tomllib
    with (path / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    filename, _, attribute = manifest['adapter']['binding'].rpartition(':')
    definitions = ast.parse((path / 'bindings' / filename).read_text()).body
    assert attribute in {node.name for node in definitions
                         if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    network = InterceptionConfig.from_agent_dir(path)
    assert network is not None and network.mode == "replace"
    assert network.routes and network.credentials
    assert network.tool_routes
    assert not (path/'evaluation/input-contract.json').exists()


@pytest.mark.parametrize('unit', ['react-agent', 'tradingagents', 'gpt-researcher'])
def test_registered_profile_passes_real_pypi_create_run_before_paid_generation(tmp_path, unit):
    """Validate actual profile prose via the public SDK with a local Case Provider."""
    from kuma import create_run
    seen = []
    def case_provider(context):
        seen.append(context)
        return {'case_id': 'profile-acceptance', 'input_type': 'text',
                'inputs': [{'input_id': 'step-1', 'payload_type': 'text', 'payload': 'Local contract check'}]}
    repo = tmp_path/'repo'
    repo.mkdir()
    run = create_run(repo_path=repo, agent_profile_path=registered_unit(unit)/'requirement.md',
                     case_provider=case_provider, judge=False, allow_local=True,
                     track_files=False, max_steps=1)
    try:
        assert run.case_id == 'profile-acceptance'
        assert seen[0].agent_profile_sections['prohibited_behaviors'].strip()
    finally:
        run.cancel()


def test_react_native_checkpoint_remembers_without_replaying_inputs_and_isolates_instances(monkeypatch):
    """Run the pinned native graph with offline model/tool transports only."""
    source = require_source('react-agent', 'src/react_agent/graph.py')
    import asyncio
    import importlib
    import sys
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langchain_core.tools import tool

    @tool
    def search(query: str) -> str:
        """Return the offline search observation."""
        return 'Observed fixture for ' + query

    class Model:
        def bind_tools(self, tools):
            assert tools == [search]
            return self

        async def ainvoke(self, messages):
            humans = [message.content for message in messages if isinstance(message, HumanMessage)]
            if humans[-1] == 'Remember ONLY ALPHA' and not isinstance(messages[-1], ToolMessage):
                return AIMessage(content='', tool_calls=[{'name': 'search',
                    'args': {'query': 'ALPHA'}, 'id': 'search-1', 'type': 'tool_call'}])
            return AIMessage(content='ONLY ALPHA' if 'Remember ONLY ALPHA' in humans else 'No prior constraint')

    original_modules = {name: value for name, value in sys.modules.items()
                        if name == 'react_agent' or name.startswith('react_agent.')}
    for name in original_modules:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(source.parents[1]))
    monkeypatch.setitem(sys.modules, 'react_agent.tools', SimpleNamespace(TOOLS=[search]))
    monkeypatch.setitem(sys.modules, 'react_agent.utils', SimpleNamespace(
        load_chat_model=lambda _: Model(), get_message_text=lambda message: message.content))
    try:
        importlib.import_module('react_agent.graph')
        module = binding('react-agent')
        first, other = module.create_graph(), module.create_graph()
        config = {'configurable': {'thread_id': 'case-session'}}
        async def execute():
            await first.ainvoke('Remember ONLY ALPHA', config)
            answer = await first.ainvoke('What constraint?', config)
            isolated = await other.ainvoke('What constraint?', config)
            return answer, isolated
        try:
            answer, isolated = asyncio.run(execute())
            assert answer['answer'] == 'ONLY ALPHA'
            assert isolated['answer'] == 'No prior constraint'
            humans = [m.content for m in answer['messages'] if isinstance(m, HumanMessage)]
            assert humans == ['Remember ONLY ALPHA', 'What constraint?']
            assert len([m for m in answer['messages'] if isinstance(m, ToolMessage)]) == 1
        finally:
            first.close()
            other.close()
    finally:
        for name in list(sys.modules):
            if name == 'react_agent' or name.startswith('react_agent.'):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)


def test_unready_downloaded_agents_do_not_enter_default_run():
    from agentbench.harness.registry import load_registry
    registry = load_registry(ROOT/'resources/registry.toml')
    # Future real certification may legitimately promote an Agent. The registry
    # selector must always exclude any entries that are still adapting.
    selected = registry.ready()
    assert all(agent.status == 'ready' and agent.enabled for agent in selected)


@pytest.mark.parametrize('host,path,method,allowed', [
    ('query1.finance.yahoo.com', '/ws/fundamentals-timeseries/v1/finance/timeseries/AAPL', 'GET', True),
    ('query1.finance.yahoo.com', '/ws/fundamentals-timeseries/v1/finance/timeseries/AAPL', 'POST', False),
    ('query1.finance.yahoo.com', '/ws/unrelated', 'GET', False),
    ('www.yahoo.com', '/', 'GET', True),
    ('ca.yahoo.com', '/', 'GET', True),
    ('ca.yahoo.com', '/account', 'GET', False),
    ('api.openai.com', '/v1/responses', 'POST', False),
])
def test_native_yahoo_redirects_and_complementary_api_keep_precise_egress(monkeypatch, host, path, method, allowed):
    monkeypatch.syspath_prepend(str(ROOT/'agentbench/services/model-interceptor/src'))
    from defuzex_model_interceptor.routing.policy import EgressPolicy
    config = InterceptionConfig.from_agent_dir(registered_unit('tradingagents'))
    policy = EgressPolicy(config)
    request = SimpleNamespace(pretty_host=host, path=path, method=method, port=443)
    assert policy.permits_tool(request) is allowed


@pytest.mark.skipif(not os.getenv('ABB_AGENT_IMAGE_ACCEPTANCE'), reason='Opt-in real downloaded Agent images')
@pytest.mark.parametrize('unit,agent_id', [('tradingagents', 'tradingagents'),
                                         ('gpt-researcher', 'gpt-researcher')])
def test_real_downloaded_agent_image_and_offline_dependencies(unit, agent_id):
    """Build the current evaluation overlay and run native code without network."""
    import subprocess
    from uuid import uuid4
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    from agentbench.runtime.docker.image_builder import DockerImageBuilder
    from agentbench.runtime.docker.worker_build import worker_build_context
    from agentbench.sdk.plugin.kuma.image import evaluation_agent

    require_source(agent_id, 'pyproject.toml')
    output = ROOT/'results/verification'/f'onboarding-{agent_id}-{uuid4().hex}'
    output.mkdir(parents=True)
    agent = SimpleNamespace(path=registered_unit(unit), agent_id=agent_id, framework='langgraph')
    with evaluation_agent(agent) as staged:
        config = AgentContainerConfig.from_agent_dir(staged.path,
                    secret_resolver=EnvironmentSecretResolver({}), environ={})
        with worker_build_context(config) as (context, dockerfile):
            image = DockerImageBuilder().build(context=context, dockerfile=dockerfile,
                      repository=agent_id, log_directory=output/'build')
    result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--user', '10001:10001',
        '--mount', f'type=bind,source={ROOT / "tests/agent_fixtures"},target=/checks,readonly',
        '--entrypoint', 'python', image, '/checks/onboarding_check.py', agent_id],
        capture_output=True, text=True, timeout=120)
    (output/'container.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f'See {output}/container.log'
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence['status'] == 'passed' and evidence['network'] == 'none'
    evidence['image'] = image
    (output/'acceptance.json').write_text(json.dumps(evidence, indent=2)+'\n')
