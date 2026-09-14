"""Issue #39: new Agent boundaries preserve real inputs and require certification."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.sdk.common.input_binding import InputBinding

ROOT = Path(__file__).resolve().parents[1]


def binding(unit, filename):
    path = ROOT/'resources/agents'/unit/'bindings'/filename
    spec = importlib.util.spec_from_file_location('onboarding_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('unit', ['03-trading-agents', '04-gpt-researcher'])
def test_new_agents_load_with_explicit_routes_and_case_conversation(unit):
    path = ROOT/'resources/agents'/unit
    config = LangGraphAdapterConfig.from_agent_dir(path)
    assert config.binding
    network = InterceptionConfig.from_agent_dir(path)
    assert network.required
    assert network.tool_routes
    input_binding = InputBinding.from_file(path/'evaluation/input-contract.json')
    first, second = input_binding.new_conversation(), input_binding.new_conversation()
    first.prepare('Remember the constraint ONLY ALPHA')
    first.commit({'status': 'succeeded', 'output': 'Acknowledged ONLY ALPHA'})
    assert 'ONLY ALPHA' in json.dumps(first.prepare('Continue'))
    assert 'ONLY ALPHA' not in json.dumps(second.prepare('Start another Case'))


def test_trading_native_graph_receives_history_callbacks_and_explicit_date(monkeypatch):
    module = binding('03-trading-agents', 'trading.py')
    seen = []
    class Graph:
        def __init__(self, **kwargs):
            seen.append(kwargs)
            self.propagator = SimpleNamespace(create_initial_state=lambda *args, **kw: kw)
            self.graph = self
        def resolve_instrument_context(self, ticker, asset):
            return ticker + ':' + asset
        def invoke(self, state, config):
            seen.append((state, config))
            return {'final_trade_decision': 'Native result for this invocation'}
    monkeypatch.setitem(__import__('sys').modules, 'tradingagents.default_config',
                        SimpleNamespace(DEFAULT_CONFIG={'data_vendors': {}}))
    monkeypatch.setitem(__import__('sys').modules, 'tradingagents.graph.trading_graph',
                        SimpleNamespace(TradingAgentsGraph=Graph))
    callbacks = [object()]
    history = [{'role': 'user', 'content': '{"ticker":"AAPL","date":"2026-09-11"}'},
               {'role': 'assistant', 'content': 'Consider uncertainty'},
               {'role': 'user', 'content': 'Now require ONLY ALPHA evidence'}]
    assert module.TradingGraph().invoke({'messages': history}, {'callbacks': callbacks})['answer'].startswith('Native result')
    state, config = seen[1]
    assert state['messages'] == history
    assert 'ONLY ALPHA' in state['past_context']
    assert config['callbacks'] is callbacks
    assert seen[0]['selected_analysts'] == ['market']
    assert not Path(seen[0]['config']['data_cache_dir']).parent.exists()


def test_trading_never_takes_identity_from_assistant_or_another_case():
    module = binding('03-trading-agents', 'trading.py')
    first = [{'role':'user', 'content':'{"ticker":"AAPL","date":"2026-09-11"}'},
             {'role':'assistant', 'content':'{"ticker":"MSFT","date":"2020-01-01"}'},
             {'role':'user', 'content':'Continue'}]
    assert module.request_from_messages(first)[:2] == ('AAPL', '2026-09-11')
    with pytest.raises(ValueError, match='ticker'):
        module.request_from_messages([{'role':'user', 'content':'Continue'}])
    with pytest.raises(ValueError, match='path'):
        module.request_from_messages([{'role':'user', 'content':'{"ticker":"../bad","date":"2026-09-11"}'}])


def test_research_query_keeps_user_corrections_and_labels_prior_reports():
    module = binding('04-gpt-researcher', 'research.py')
    history = [{'role':'user', 'content':'Compare alpha and beta'},
               {'role':'assistant', 'content':'A prior report'},
               {'role':'user', 'content':'Correction: use only beta'}]
    query = module.query_from_messages({'messages':history})
    assert all(m['content'] in query for m in history)
    assert 'not verified new sources' in query
    assert module.query_from_messages({'messages':[{'role':'user','content':'Fresh'}]}) == 'Fresh'


def test_unready_downloaded_agents_do_not_enter_default_run():
    from agentbench.harness.registry import load_registry
    registry = load_registry(ROOT/'resources/registry.toml')
    # Future real certification may legitimately promote an Agent. The registry
    # selector must always exclude any entries that are still adapting.
    selected = registry.ready()
    assert all(agent.status == 'ready' and agent.enabled for agent in selected)


@pytest.mark.skipif(not os.getenv('ABB_AGENT_IMAGE_ACCEPTANCE'), reason='Opt-in real downloaded Agent images')
@pytest.mark.parametrize('unit,agent_id', [('03-trading-agents', 'trading-agents'),
                                         ('04-gpt-researcher', 'gpt-researcher')])
def test_real_downloaded_agent_image_and_offline_dependencies(unit, agent_id):
    """Build the current evaluation overlay and run native code without network."""
    import subprocess
    from uuid import uuid4
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    from agentbench.runtime.docker.image_builder import DockerImageBuilder
    from agentbench.runtime.docker.worker_build import worker_build_context
    from agentbench.sdk.plugin.kuma.image import evaluation_agent

    output = ROOT/'results/verification'/f'onboarding-{agent_id}-{uuid4().hex}'
    output.mkdir(parents=True)
    agent = SimpleNamespace(path=ROOT/'resources/agents'/unit, agent_id=agent_id, framework='langgraph')
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
