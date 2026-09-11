"""Offline regressions: actual transports, runtime context and evidence artifacts."""
import asyncio
import importlib
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import TypedDict

import pytest

from agentbench.observe.correlation import HEADER, current_span, model_correlation


@pytest.fixture
def upstream():
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get(HEADER)))
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', f'http://localhost:{self.server.server_port}/final')
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            received.append((self.path, self.headers.get(HEADER)))
            body = {'id': 'offline', 'object': 'chat.completion', 'created': 1, 'model': 'fixture',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'done'}, 'finish_reason': 'stop'}]}
            if self.path == '/search':
                body = {'query': 'fixture', 'results': [], 'response_time': 0.01}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('transport', ['httpx', 'httpx2', 'requests', 'aiohttp'])
def test_real_transport_redirect_and_scope_cleanup(upstream, transport):
    module = pytest.importorskip(transport)
    base, received = upstream
    def request(path):
        if transport == 'aiohttp':
            async def call():
                async with module.ClientSession() as client:
                    async with client.get(base + path) as response:
                        await response.read()
            asyncio.run(call())
        elif transport == 'requests':
            with module.Session() as client:
                client.trust_env = False
                client.get(base + path)
        else:
            with module.Client(trust_env=False, follow_redirects=True) as client:
                client.get(base + path)
    with model_correlation(['127.0.0.1']):
        token = current_span.set('framework-one')
        try:
            request('/redirect')
        finally:
            current_span.reset(token)
    request('/outside')
    assert received == [('/redirect', 'framework-one'), ('/final', None), ('/outside', None)]


@pytest.mark.parametrize('transport', ['httpx', 'httpx2'])
def test_async_concurrent_scopes_and_reused_request(transport):
    module = pytest.importorskip(transport)
    seen = []
    async def handler(request):
        await asyncio.sleep(0)
        seen.append((request.url.path, request.headers.get(HEADER)))
        return module.Response(200)
    async def run():
        async with module.AsyncClient(transport=module.MockTransport(handler)) as client:
            async def call(name):
                request = client.build_request('GET', f'https://example.test/{name}')
                with model_correlation(['example.test']):
                    current_span.set(name)
                    await client.send(request)
                assert HEADER not in request.headers
                await client.send(request)
            await asyncio.gather(call('one'), call('two'))
    asyncio.run(run())
    assert sorted(seen, key=str) == sorted([('/one', 'one'), ('/two', 'two'), ('/one', None), ('/two', None)], key=str)


@pytest.mark.parametrize('model', ['dataclass', 'pydantic'])
@pytest.mark.parametrize('asynchronous', [False, True])
def test_real_langgraph_runtime_context(tmp_path, model, asynchronous):
    from langgraph.graph import StateGraph, START, END
    from langgraph.runtime import Runtime
    from pydantic import BaseModel
    from agentbench.adapter.langgraph.adapter import LangGraphAdapter
    from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
    class State(TypedDict):
        answer: str
    @dataclass
    class Context:
        prefix: str = 'default'
    class ModelContext(BaseModel):
        prefix: str = 'default'
    schema = Context if model == 'dataclass' else ModelContext
    def node(state, runtime: Runtime):
        return {'answer': runtime.context.prefix}
    graph = StateGraph(State, context_schema=schema).add_node('read', node)
    graph.add_edge(START, 'read').add_edge('read', END)
    adapter = LangGraphAdapter(LangGraphAdapterConfig(tmp_path, 'fixture', 'unused:g', None, 'answer', 'in_process', context={'prefix': 'configured'}))
    adapter._graph = graph.compile()
    result = asyncio.run(adapter.ainvoke({})) if asynchronous else adapter.invoke({})
    assert result.output == 'configured'


def test_host_evidence_and_public_judge(starter_agent, tmp_path):
    from agentbench.harness import BenchmarkRunner
    from agentbench.observe.host import host_observation_factory
    from agentbench.observe.view_api import RunViewAPI
    from tests.test_benchmark_runner import FakeSDKRun
    progress = []
    result = BenchmarkRunner(observation_factory=host_observation_factory(tmp_path)).run(starter_agent, FakeSDKRun(), on_progress=progress.append)
    directory = next(tmp_path.iterdir())
    api = RunViewAPI(directory)
    metadata = api.read('run.json')
    assert metadata['status'] == 'succeeded'
    assert metadata['evidence_availability']['network']['status'] == 'unavailable'
    assert api.evaluation()['public_result']['report']['status'] == result.report.status
    assert api.spans()['spans']
    assert any(row['attributes'].get('abb.framework_span_id') for row in api.spans()['spans'])
    assert any(event.artifact_directory == str(directory) for event in progress)


def test_shared_provider_has_bounded_processors(tmp_path):
    from opentelemetry.sdk.trace import TracerProvider
    from agentbench.observe.invocation import InvocationObservation
    provider = TracerProvider()
    for i in range(5):
        observed = InvocationObservation(tmp_path / str(i), str(i), 'session', 'langgraph', provider=provider)
        observed.store.record('execution_start', input='test')
        observed.store.record('execution_end', output='done')
        observed.close()
    assert len(provider._active_span_processor._span_processors) == 1
    assert not provider._disabled
    provider.shutdown()


def test_correlation_gaps_are_visible(tmp_path):
    from agentbench.observe.interactions import interactions
    rows = [{'source': 'interceptor', 'event': 'llm_request', 'data': {'call_id': 'one', 'framework_span_id': 'nonexistent'}}]
    (tmp_path / 'network.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    result = interactions(tmp_path, {})
    assert result['correlation'] == {'requests': 1, 'linked': 0, 'uncorrelated': 1, 'status': 'captured'}
    assert any('no matching framework span' in warning for warning in result['warnings'])


@pytest.mark.parametrize('cancelled', [False, True])
def test_failed_host_retains_redacted_artifacts(starter_agent, tmp_path, monkeypatch, cancelled):
    from agentbench.harness import BenchmarkRunner, AgentInvocationError
    from agentbench.harness.runner.running_agent import RunningAgent
    from agentbench.observe.host import host_observation_factory
    from tests.test_benchmark_runner import FakeSDKRun
    monkeypatch.setenv('FIXTURE_API_KEY', 'do-not-persist-this')
    closed = []
    class Adapter:
        is_loaded = True
        async def ainvoke(self, *args, **kw):
            if cancelled:
                raise asyncio.CancelledError()
            raise ValueError('original cause do-not-persist-this')
        async def aclose(self):
            closed.append(True)
    handle = RunningAgent(starter_agent, Adapter())
    runner = BenchmarkRunner(agent_runner=SimpleNamespace(start=lambda _: handle), observation_factory=host_observation_factory(tmp_path))
    with pytest.raises(asyncio.CancelledError if cancelled else AgentInvocationError) as caught:
        runner.run(starter_agent, FakeSDKRun())
    assert closed == [True]
    metadata = json.loads(next(tmp_path.glob('*/run.json')).read_text())
    assert metadata['status'] == ('cancelled' if cancelled else 'failed')
    assert list(tmp_path.glob('*/evaluation/inputs/*/result.json'))
    assert all('do-not-persist-this' not in file.read_text() for file in tmp_path.rglob('*') if file.is_file())
    if not cancelled:
        assert 'original cause [REDACTED]' in str(caught.value)


def test_real_openai_and_tavily_clients(upstream):
    AsyncOpenAI = pytest.importorskip('openai').AsyncOpenAI
    AsyncTavilyClient = pytest.importorskip('tavily').AsyncTavilyClient
    base, received = upstream
    async def run():
        async with AsyncOpenAI(api_key='offline', base_url=base + '/v1') as client:
            with model_correlation(['127.0.0.1']):
                current_span.set('llm-span')
                response = await client.chat.completions.create(model='fixture', messages=[{'role': 'user', 'content': 'hello'}])
                assert response.choices[0].message.content == 'done'
        client = AsyncTavilyClient(api_key='offline', api_base_url=base)
        try:
            with model_correlation(['127.0.0.1']):
                current_span.set('tool-span')
                assert (await client.search('fixture'))['results'] == []
        finally:
            await client.close()
    asyncio.run(run())
    assert received == [('/v1/chat/completions', 'llm-span'), ('/search', 'tool-span')]


def test_host_observation_is_limited_to_in_process_agents(starter_agent, tmp_path):
    """A containerised Agent must not receive host callbacks in its run_config.

    The container invocation envelope is JSON, and the worker rejects host
    callbacks outright, so a HostObservation on that path makes json.dumps fail
    before the Agent runs.
    """
    import shutil
    from dataclasses import replace

    from agentbench.observe.host import HostObservation, host_observation_factory

    observe = host_observation_factory(tmp_path / 'observe')
    run = SimpleNamespace(run_id='run-1')

    assert isinstance(observe(starter_agent, run), HostObservation)

    containerised = tmp_path / 'docker-agent'
    shutil.copytree(starter_agent.path, containerised)
    (containerised / 'agent.toml').write_text(
        (containerised / 'agent.toml').read_text(encoding='utf-8')
        + '\n[runtime]\ntype = "docker"\nexecution = "oneshot"\n',
        encoding='utf-8',
    )
    assert observe(replace(starter_agent, path=containerised), run) is None


@pytest.mark.parametrize('failure', [EOFError(), OSError('captured stdin')])
def test_prompts_survive_a_console_that_cannot_answer(failure):
    """A finished evaluation must not be reported as failed by its own prompt.

    pytest's captured stdin raises OSError rather than EOFError, which
    previously escaped and turned a completed run into a non-zero exit.
    """
    from pathlib import Path

    from agentbench.cli.terminal_ui.presentation import (
        request_confirmation,
        request_viewer_action,
    )

    def refuse(_prompt):
        raise failure

    assert request_confirmation(refuse, lambda _: None) is False
    assert request_viewer_action(
        Path('result.json'), 'http://localhost/test',
        input_fn=refuse, output_fn=lambda _: None,
    ) == 'quit'


def test_unexpected_prompt_errors_still_surface():
    """Only an unusable console is absorbed; real defects must still raise."""
    from pathlib import Path

    from agentbench.cli.terminal_ui.presentation import request_viewer_action

    def broken(_prompt):
        raise RuntimeError('input failed')

    with pytest.raises(RuntimeError, match='input failed'):
        request_viewer_action(
            Path('result.json'), 'http://localhost/test',
            input_fn=broken, output_fn=lambda _: None,
        )
