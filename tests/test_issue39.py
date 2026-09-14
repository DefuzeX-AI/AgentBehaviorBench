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
    import ast
    path = ROOT/'resources/agents'/unit
    config = LangGraphAdapterConfig.from_agent_dir(path)
    assert config.binding
    source, _, attribute = config.entrypoint.rpartition(':')
    definitions = ast.parse((config.source_root/source).read_text()).body
    assert attribute in {node.name for node in definitions
                         if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    network = InterceptionConfig.from_agent_dir(path)
    assert network.required
    assert network.tool_routes
    input_binding = InputBinding.from_file(path/'evaluation/input-contract.json')
    first, second = input_binding.new_conversation(), input_binding.new_conversation()
    first.prepare('Remember the constraint ONLY ALPHA')
    first.commit({'status': 'succeeded', 'output': 'Acknowledged ONLY ALPHA'})
    assert 'ONLY ALPHA' in json.dumps(first.prepare('Continue'))
    assert 'ONLY ALPHA' not in json.dumps(second.prepare('Start another Case'))


@pytest.mark.parametrize('unit', ['02-react-agent', '03-trading-agents', '04-gpt-researcher'])
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
    run = create_run(repo_path=repo, agent_profile_path=ROOT/'resources/agents'/unit/'evaluation/profile.md',
                     case_provider=case_provider, judge=False, allow_local=True,
                     track_files=False, max_steps=1)
    try:
        assert run.case_id == 'profile-acceptance'
        assert seen[0].agent_profile_sections['prohibited_behaviors'].strip()
    finally:
        run.cancel()


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


def test_research_langgraph_boundary_delivers_history_and_returns_native_report(monkeypatch):
    import asyncio
    module = binding('04-gpt-researcher', 'research.py')
    delivered = []
    async def research(self, value, config=None, **kwargs):
        delivered.append(value['messages'])
        return {'answer': 'Native report', 'sources': ['https://arxiv.org/abs/example']}
    monkeypatch.setattr(module.ResearchGraph, 'ainvoke', research)
    history = [{'role': 'user', 'content': 'Remember ONLY ALPHA'},
               {'role': 'assistant', 'content': 'Understood'},
               {'role': 'user', 'content': 'Continue'}]
    output = asyncio.run(module.create_graph().ainvoke({'messages': history}))
    assert delivered == [history]
    assert output['answer'] == 'Native report'
    assert output['sources'] == ['https://arxiv.org/abs/example']


@pytest.mark.parametrize('has_sources', [True, False])
def test_research_observes_native_full_text_and_preserves_sources_for_judge(monkeypatch, has_sources):
    import asyncio
    import sys
    module = binding('04-gpt-researcher', 'research.py')
    source = 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/'
    native_result = [{'href': source, 'raw_content': 'Observed article full text'}]
    seen = []

    class NativeSearch:
        requires_scraping = False
        def __init__(self, query):
            self.query = query
        def search(self, max_results=5):
            seen.append((self.query, max_results))
            return native_result

    class NativeResearcher:
        def __init__(self, **kwargs):
            self.query = kwargs['query']
            self.cfg = SimpleNamespace(llm_kwargs={})
        async def conduct_research(self):
            retriever = self.retrievers[0](self.query)
            assert retriever.requires_scraping is False
            assert retriever.search(max_results=1) is native_result
        async def write_report(self):
            return 'Original native report'
        def get_source_urls(self):
            return [source] if has_sources else []

    monkeypatch.setitem(sys.modules, 'gpt_researcher', SimpleNamespace(GPTResearcher=NativeResearcher))
    monkeypatch.setitem(sys.modules, 'gpt_researcher.retrievers.pubmed_central.pubmed_central',
                        SimpleNamespace(PubMedCentralSearch=NativeSearch))
    invocation = module.ResearchGraph().ainvoke({'query': 'Biomedical evidence'}, {'callbacks': []})
    assert asyncio.run(invocation) == {'answer': 'Original native report',
                                      'sources': [source] if has_sources else []}
    assert seen == [('Biomedical evidence', 1)]


def test_pubmed_parallel_requests_share_cooldown_even_after_failure():
    from concurrent.futures import ThreadPoolExecutor
    import time
    module = binding('04-gpt-researcher', 'research.py')
    gate = module.PubMedRequestGate(interval=0.03)
    starts = []
    def request(number):
        starts.append(time.monotonic())
        if number == 1:
            raise RuntimeError('Native request failed')
        return number
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(gate.call, request, number) for number in range(3)]
        assert futures[0].result() == 0
        with pytest.raises(RuntimeError, match='Native request failed'):
            futures[1].result()
        assert futures[2].result() == 2
    assert len(starts) == 3
    assert all(b - a >= 0.03 for a, b in zip(starts, starts[1:]))


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
