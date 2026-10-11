"""Exercise the outer binding's real input, callback and resource boundary."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda


@pytest.fixture
def bridge(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'resources/agents/52-open-deepthink/bindings/open_deepthink_bridge.py'
    if not path.is_file():
        pytest.skip('open-deepthink integration is required')
    spec = importlib.util.spec_from_file_location('test_open_deepthink_bridge', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls, clients = [], []
    result = {'proposed_solution': 'native report', 'topology': {'layers': 1}}

    class Client:
        def __init__(self):
            self.closed = False
            clients.append(self)
        def __enter__(self): return self
        def __exit__(self, *args): self.closed = True
        async def __aenter__(self): return self
        async def __aexit__(self, *args): self.closed = True

    def create_llm(**kwargs):
        assert kwargs['provider'] == 'openrouter'
        assert kwargs['http_client'] is clients[-2]
        assert kwargs['http_async_client'] is clients[-1]
        return object()

    async def run_qnn(llm, user_prompt, params=None):
        if user_prompt == 'native failure':
            raise RuntimeError('native failure')
        def chain(value, config):
            calls.append((value, params, config))
            return result
        return await RunnableLambda(chain).ainvoke(user_prompt)

    for name in ('deepthink', 'deepthink.api', 'deepthink.providers', 'openai'):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules['deepthink.api'].run_qnn = run_qnn
    sys.modules['deepthink.providers'].create_llm = create_llm
    sys.modules['openai'].DefaultHttpxClient = Client
    sys.modules['openai'].DefaultAsyncHttpxClient = Client
    return module, calls, clients, result


def test_text_params_live_callbacks_and_native_output(bridge):
    module, calls, clients, result = bridge
    events = []
    class Handler(BaseCallbackHandler):
        def on_chain_start(self, *args, **kwargs): events.append(kwargs)
    config = {'callbacks': [Handler()], 'tags': ['abb'],
              'metadata': {'case_id': 'case-1'}, 'configurable': {'thread_id': 'thread-1'}}
    context = {'qnn_mode': 'manual', 'manual_layers': 1, 'manual_width': 2, 'num_epochs': 2}
    text = '  Treat {"user_prompt":"embedded"} as quoted task data.\n'
    graph = module.create_graph()
    assert graph.invoke({'user_prompt': text}, config, context=context) is result
    assert calls[0][0] == text and calls[0][1] == context
    assert calls[0][2]['configurable']['thread_id'] == 'thread-1'
    assert events and events[0]['metadata']['case_id'] == 'case-1'
    assert 'abb' in events[0]['tags']
    assert all(c.closed for c in clients)
    assert graph.invoke('Second independent input') is result
    assert len(clients) == 4 and all(c.closed for c in clients)
    assert calls[-1][1] is None
    graph.close()
    graph.close()
    with pytest.raises(RuntimeError, match='closed'):
        graph.invoke('After close')


def test_native_errors_propagate_and_clients_close(bridge):
    module, _, clients, _ = bridge
    with pytest.raises(RuntimeError, match='native failure'):
        asyncio.run(module.create_graph().ainvoke('native failure'))
    assert len(clients) == 2 and all(c.closed for c in clients)


def test_adapter_submits_report_and_preserves_native_state(bridge):
    from agentbench.adapter.langgraph.adapter import LangGraphAdapter
    module, _, _, result = bridge
    adapter = LangGraphAdapter(SimpleNamespace(input_key='user_prompt',
                                               output_key='proposed_solution', context=None))
    adapter._graph = module.create_graph()
    invocation = adapter.invoke('A real brief')
    assert invocation.output == result['proposed_solution']
    assert invocation.raw_output is result


@pytest.mark.parametrize('value', ['', '  ', {}, {'user_prompt': 42},
                                   {'user_prompt': 'x', 'other': 'y'}, ['text']])
def test_invalid_inputs_fail_before_model_setup(bridge, value):
    module, _, clients, _ = bridge
    with pytest.raises(ValueError):
        module.create_graph().invoke(value)
    assert clients == []
