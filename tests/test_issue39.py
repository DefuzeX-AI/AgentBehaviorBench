"""Issue #39: new Agent boundaries preserve real inputs and require certification."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.sdk.common.input_binding import validate_input_contract

ROOT = Path(__file__).resolve().parents[1]


def binding(unit, filename):
    path = ROOT/'resources/agents'/unit/'bindings'/filename
    spec = importlib.util.spec_from_file_location('onboarding_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('unit', ['03-trading-agents', '04-gpt-researcher'])
def test_new_agents_load_with_explicit_routes_and_current_input_contract(unit):
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
    validate_input_contract(path/'evaluation/input-contract.json')
    assert json.loads((path/'evaluation/input-contract.json').read_text()) == {'encoding': 'identity'}


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
    run = create_run(repo_path=repo, agent_profile_path=ROOT/'resources/agents'/unit/'requirement.md',
                     case_provider=case_provider, judge=False, allow_local=True,
                     track_files=False, max_steps=1)
    try:
        assert run.case_id == 'profile-acceptance'
        assert seen[0].agent_profile_sections['prohibited_behaviors'].strip()
    finally:
        run.cancel()


def test_react_native_checkpoint_remembers_without_replaying_inputs_and_isolates_instances(monkeypatch):
    """Run the pinned native graph with offline model/tool transports only."""
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
    monkeypatch.syspath_prepend(str(ROOT/'resources/agents/02-react-agent/agent/src'))
    monkeypatch.setitem(sys.modules, 'react_agent.tools', SimpleNamespace(TOOLS=[search]))
    monkeypatch.setitem(sys.modules, 'react_agent.utils', SimpleNamespace(
        load_chat_model=lambda _: Model(), get_message_text=lambda message: message.content))
    try:
        importlib.import_module('react_agent.graph')
        module = binding('02-react-agent', 'react.py')
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


def test_trading_public_entrypoint_receives_explicit_parameters_and_keeps_native_files(monkeypatch):
    from langchain_core.runnables.config import ensure_config
    module = binding('03-trading-agents', 'trading.py')
    seen = []
    class Graph:
        def __init__(self, **kwargs):
            seen.append(kwargs)
            self.cache = Path(kwargs['config']['data_cache_dir'])
            self.cache.mkdir()
        def propagate(self, ticker, trade_date, *, asset_type):
            seen.append((ticker, trade_date, asset_type, ensure_config()))
            (self.cache/'native-agent-state').write_text('Created by the native agent')
            return {'market_report': 'Native detailed report', 'final_trade_decision': 'Hold'}, 'Hold'
    monkeypatch.setitem(__import__('sys').modules, 'tradingagents.default_config',
                        SimpleNamespace(DEFAULT_CONFIG={'data_vendors': {}}))
    monkeypatch.setitem(__import__('sys').modules, 'tradingagents.graph.trading_graph',
                        SimpleNamespace(TradingAgentsGraph=Graph))
    callbacks = [object()]
    session = module.TradingGraph()
    try:
        output = session.invoke({'ticker': 'MSFT', 'date': '2026-09-10'}, {'callbacks': callbacks})
        assert output == {'final_state': {'market_report': 'Native detailed report',
                                         'final_trade_decision': 'Hold'}, 'decision': 'Hold'}
        assert seen[1][:3] == ('MSFT', '2026-09-10', 'stock')
        assert seen[1][3]['callbacks'] == callbacks
        assert seen[0]['selected_analysts'] == ['market']
        cache = Path(seen[0]['config']['data_cache_dir'])
        assert (cache/'native-agent-state').read_text() == 'Created by the native agent'
        session.invoke('{"ticker":"AAPL","date":"2026-09-11"}')
        assert len(seen) == 3  # One native instance, two public task calls.
        assert seen[2][:3] == ('AAPL', '2026-09-11', 'stock')
        assert (cache/'native-agent-state').is_file()
    finally:
        session.close()
    assert not cache.parent.exists()


def test_trading_requires_current_native_parameters_without_implicit_defaults():
    module = binding('03-trading-agents', 'trading.py')
    current = {'ticker': 'AAPL', 'date': '2026-09-11'}
    assert module.request_from_input(current) == ('AAPL', '2026-09-11')
    assert module.request_from_input(json.dumps(current)) == ('AAPL', '2026-09-11')
    with pytest.raises(ValueError, match='ticker'):
        module.request_from_input('Continue')
    with pytest.raises(ValueError, match='path'):
        module.request_from_input({'ticker': '../bad', 'date': '2026-09-11'})
    for unsupported in ({'messages': []}, {**current, 'request': 'Old research question'},
                        {'date': '2026-09-11'}, {'ticker': 'MSFT'}):
        with pytest.raises(ValueError, match='exactly ticker and date'):
            module.request_from_input(unsupported)


def test_research_query_preserves_current_text_and_rejects_synthetic_history():
    module = binding('04-gpt-researcher', 'research.py')
    history = [{'role':'user', 'content':'Compare alpha and beta'},
               {'role':'assistant', 'content':'A prior report'},
               {'role':'user', 'content':'Correction: use only beta'}]
    with pytest.raises(ValueError, match='history'):
        module.query_from_input({'messages': history})
    current = 'Correction: use only beta'
    assert module.query_from_input(current) == current
    assert module.query_from_input({'query': current}) == current
    with pytest.raises(ValueError, match='non-empty'):
        module.query_from_input({'query': '  '})


def test_research_langgraph_boundary_researches_once_then_delivers_current_chat(monkeypatch):
    import asyncio
    module = binding('04-gpt-researcher', 'research.py')
    delivered, requests = [], []
    async def research(self, value, config=None, **kwargs):
        delivered.append(value['query'])
        return {'answer': 'Native report', 'sources': ['https://arxiv.org/abs/example']}
    monkeypatch.setattr(module.ResearchGraph, 'ainvoke', research)
    class ReportAPI:
        async def post(self, path, payload):
            requests.append((path, payload))
            if path == '/api/reports':
                return {'success': True, 'id': payload['id']}
            return {'success': True, 'response': {'role': 'assistant', 'content': 'Native report follow-up'}}
        def close(self):
            pass
    monkeypatch.setattr(module, 'NativeReportAPI', ReportAPI)
    graph = module.create_graph()
    try:
        first = asyncio.run(graph.ainvoke({'query': 'Remember ONLY ALPHA'}))
        output = asyncio.run(graph.ainvoke({'query': 'Continue'}))
        assert delivered == ['Remember ONLY ALPHA']
        assert first['answer'] == 'Native report'
        assert first['sources'] == ['https://arxiv.org/abs/example']
        assert output['answer'] == 'Native report follow-up'
        assert requests[0][1]['answer'] == 'Native report'
        assert requests[1][1] == {'role': 'user', 'content': 'Continue'}
    finally:
        graph.close()


@pytest.mark.parametrize('visited,prefetched', [(True, False), (False, True), (True, True), (False, False)])
def test_research_observes_native_full_text_and_preserves_sources_for_judge(monkeypatch, visited, prefetched):
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
        async def write_report(self, *, custom_prompt):
            assert self.query in custom_prompt
            return 'Original native report'
        def get_source_urls(self):
            return [source] if visited else []
        def get_research_sources(self):
            return [{'url': source}] if prefetched else []

    monkeypatch.setitem(sys.modules, 'gpt_researcher', SimpleNamespace(GPTResearcher=NativeResearcher))
    monkeypatch.setitem(sys.modules, 'gpt_researcher.retrievers.pubmed_central.pubmed_central',
                        SimpleNamespace(PubMedCentralSearch=NativeSearch))
    invocation = module.ResearchGraph().ainvoke({'query': 'Biomedical evidence'}, {'callbacks': []})
    assert asyncio.run(invocation) == {'answer': 'Original native report',
                                      'sources': [source] if visited or prefetched else []}
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


@pytest.mark.parametrize('scenario', ['single', 'unicode', 'long_query'])
def test_native_pubmed_transport_preserves_current_query_and_native_parser(monkeypatch, scenario):
    """Exercise the real upstream retriever through ABB's observed binding.

    A bounded HTTP double reproduces NCBI's 414 response for long GET URLs.
    The current query passes unchanged to the native researcher and retriever.
    A long standalone search uses form POST without truncation.
    """
    import asyncio
    import sys
    import requests

    module = binding('04-gpt-researcher', 'research.py')
    module._PUBMED_REQUESTS = module.PubMedRequestGate(interval=0)
    source = ROOT/'resources/agents/04-gpt-researcher/agent/gpt_researcher/retrievers/pubmed_central/pubmed_central.py'
    spec = importlib.util.spec_from_file_location('native_pubmed', source)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    expected_query = 'Find clinical evidence for cancer therapy'
    if scenario == 'unicode':
        expected_query = 'Find clinical evidence 癌症证据'
    elif scenario == 'long_query':
        expected_query = 'cancer therapy ' * 500
    calls = []

    def respond(method, url, *, params=None, data=None, **kwargs):
        assert url.startswith('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/')
        request = requests.Request(method, url, params=params, data=data).prepare()
        calls.append((method, url, params if params is not None else data))
        response = requests.Response()
        response.request, response.url = request, request.url
        response.status_code = 414 if len(request.url.encode()) > 4096 else 200
        if url.endswith('esearch.fcgi'):
            response._content = b'{"esearchresult":{"idlist":["123"]}}'
        else:
            assert url.endswith('efetch.fcgi') and method == 'GET'
            response._content = b'<article><article-title>Real parser fixture</article-title><abstract>Evidence</abstract><body>Full text</body></article>'
        return response

    monkeypatch.setattr(requests, 'get', lambda url, **kw: respond('GET', url, **kw))
    monkeypatch.setattr(requests, 'post', lambda url, **kw: respond('POST', url, **kw))

    class NativeResearcher:
        def __init__(self, **kwargs):
            self.query = kwargs['query']
            self.cfg = SimpleNamespace(llm_kwargs={})
            self.sources = []
        async def conduct_research(self):
            assert self.query == expected_query
            self.sources = self.retrievers[0](self.query).search(max_results=1)
            self.sources += self.retrievers[0]('Model-planned clinical search').search(max_results=1)
        async def write_report(self, *, custom_prompt):
            assert self.query == expected_query
            assert expected_query in custom_prompt
            return 'Native report fixture'
        def get_source_urls(self):
            return []
        def get_research_sources(self):
            return self.sources

    monkeypatch.setitem(sys.modules, 'gpt_researcher', SimpleNamespace(GPTResearcher=NativeResearcher))
    monkeypatch.setitem(sys.modules, 'gpt_researcher.retrievers.pubmed_central.pubmed_central', native)
    result = asyncio.run(module.ResearchGraph().ainvoke({'query': expected_query}))
    assert result['sources'] == ['https://www.ncbi.nlm.nih.gov/pmc/articles/123/']
    assert len(calls) == 4  # Two distinct searches/fetches, no retry of either.
    assert calls[0][0] == ('POST' if scenario == 'long_query' else 'GET')
    assert calls[0][2]['term'] == expected_query
    assert calls[0][2]['retmax'] == 1
    assert calls[1][0] == 'GET'
    assert calls[2][0] == 'GET' and calls[2][2]['term'] == 'Model-planned clinical search'


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
    config = InterceptionConfig.from_agent_dir(ROOT/'resources/agents/03-trading-agents')
    policy = EgressPolicy(config)
    request = SimpleNamespace(pretty_host=host, path=path, method=method, port=443)
    assert policy.permits_tool(request) is allowed


@pytest.mark.parametrize('host,path,method,allowed', [
    ('eutils.ncbi.nlm.nih.gov', '/entrez/eutils/esearch.fcgi', 'POST', True),
    ('eutils.ncbi.nlm.nih.gov', '/entrez/eutils/esearch.fcgi', 'GET', True),
    ('eutils.ncbi.nlm.nih.gov', '/entrez/eutils/efetch.fcgi', 'POST', False),
    ('eutils.ncbi.nlm.nih.gov', '/entrez/eutils/epost.fcgi', 'POST', False),
    ('api.openai.com', '/v1/chat/completions', 'POST', False),
])
def test_pubmed_form_search_has_an_exact_egress_route(monkeypatch, host, path, method, allowed):
    monkeypatch.syspath_prepend(str(ROOT/'agentbench/services/model-interceptor/src'))
    from defuzex_model_interceptor.routing.policy import EgressPolicy
    config = InterceptionConfig.from_agent_dir(ROOT/'resources/agents/04-gpt-researcher')
    request = SimpleNamespace(pretty_host=host, path=path, method=method, port=443)
    assert EgressPolicy(config).permits_tool(request) is allowed


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
