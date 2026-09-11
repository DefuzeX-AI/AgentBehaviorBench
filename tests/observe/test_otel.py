import json
from concurrent.futures import ThreadPoolExecutor
from opentelemetry.sdk.trace import TracerProvider
from agentbench.observe.otel.session import OtelSession


def rows(path):
    return [json.loads(line)['data'] for line in path.open()]


def test_parallel_nested_spans_large_payload_and_error(tmp_path):
    session = OtelSession(tmp_path, 'invocation', 'run', ('secret-value',))
    session.record('execution_start', input='hello')
    session.record('span_start', span_id='parent', name='graph', input={})
    large = '中文\u2028完整' * 100000
    def child(number):
        session.record('span_start', span_id=str(number), parent_span_id='parent', name='child', input=large)
        session.record('span_end', span_id=str(number), output=large)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(child, (1, 2)))
    session.record('span_start', span_id='error', parent_span_id='parent', name='bad', input='secret-value')
    session.record('span_error', span_id='error', error='secret-value failed')
    session.record('span_end', span_id='parent', output='done')
    session.record('execution_end', output='done')
    session.close()
    spans = rows(tmp_path / 'otel.jsonl')
    assert len(spans) == 5
    assert len({s['trace_id'] for s in spans}) == 1
    graph = next(s for s in spans if s['name'] == 'graph')
    assert all(s['parent_span_id'] == graph['span_id'] for s in spans if s['name'] == 'child')
    assert next(s for s in spans if s['name'] == 'bad')['status']['status_code'] == 'ERROR'
    child_span = next(s for s in spans if s['name'] == 'child')
    assert json.loads((tmp_path / child_span['attributes']['abb.output_ref']).read_text()) == large
    assert all('secret-value' not in f.read_text() for f in (tmp_path / 'otel-payloads').iterdir())
    assert json.loads((tmp_path / 'otel-status.json').read_text())['status'] == 'complete'


def test_shared_provider_is_not_shutdown_and_runs_do_not_mix(tmp_path):
    provider = TracerProvider()
    for name in ('first', 'second'):
        folder = tmp_path / name; folder.mkdir()
        session = OtelSession(folder, name, name, provider=provider)
        session.record('execution_start', input=name)
        session.record('execution_end', output=name)
        session.close()
        assert len(rows(folder / 'otel.jsonl')) == 1
    assert len(rows(tmp_path / 'first/otel.jsonl')) == 1
    provider.shutdown()


def test_unclosed_step_is_marked_incomplete(tmp_path):
    session = OtelSession(tmp_path, 'i', 'r')
    session.record('execution_start', input={})
    session.record('span_start', span_id='unfinished', name='unfinished', input={})
    session.close()
    assert json.loads((tmp_path / 'otel-status.json').read_text())['status'] == 'incomplete'
    assert next(s for s in rows(tmp_path / 'otel.jsonl') if s['name']=='unfinished')['attributes']['abb.incomplete']


def test_full_native_events_survive_otel_inline_limit_and_summary(tmp_path):
    from agentbench.observe.store import summarize
    session = OtelSession(tmp_path, 'native', 'run')
    session.record('execution_start', input={})
    for index in range(400):
        session.record('native_event', name='chunk', value=f'中文\u2028{index}')
    session.record('execution_end', output='done')
    session.close()
    span = rows(tmp_path / 'otel.jsonl')[0]
    saved = [json.loads(line) for line in (tmp_path / span['attributes']['abb.events_ref']).open()]
    assert len(saved) == 400 and saved[-1]['data']['value'] == '中文\u2028399'
    assert summarize(tmp_path)['otel-payload:chunk'] == 400


def test_real_async_langgraph_callbacks(tmp_path):
    import asyncio
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END
    from agentbench.observe.store import TraceStore
    from agentbench.observe.otel.session import ObservedStore
    from agentbench.observe.observers import DEFAULT_OBSERVERS
    class State(TypedDict):
        input: int
        left: int
        right: int
    async def left(value):
        await asyncio.sleep(0)
        return {'left': value['input'] * 2}
    async def right(value):
        await asyncio.sleep(0)
        return {'right': value['input'] + 3}
    graph = StateGraph(State)
    graph.add_node('left', left); graph.add_node('right', right)
    graph.add_edge(START, 'left'); graph.add_edge(START, 'right')
    graph.add_edge('left', END); graph.add_edge('right', END)
    store = ObservedStore(TraceStore(tmp_path / 'framework.jsonl', 'sample'), 'sample')
    store.record('execution_start', input={'input': 4})
    result = asyncio.run(graph.compile().ainvoke({'input': 4}, config={'callbacks': DEFAULT_OBSERVERS.callbacks('langgraph', store)}))
    store.record('execution_end', output=result); store.close()
    assert result['left'] == 8 and result['right'] == 7
    spans = rows(tmp_path / 'otel.jsonl')
    children = [s for s in spans if s['name'] in ('left', 'right')]
    assert len(children) == 2 and children[0]['parent_span_id'] == children[1]['parent_span_id']
    assert json.loads((tmp_path / 'otel-status.json').read_text())['status'] == 'complete'
