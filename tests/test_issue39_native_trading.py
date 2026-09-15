"""Native Trading public API, callback inheritance and Agent-owned memory."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT/'resources/agents/03-trading-agents'


def binding():
    spec = importlib.util.spec_from_file_location('native_trading_binding', UNIT/'bindings/trading.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('value', [
    {'ticker': 'AAPL', 'date': '2026-09-11'},
    '{"ticker":"AAPL","date":"2026-09-11"}',
])
def test_native_arguments_are_explicit_and_unchanged(value):
    assert binding().request_from_input(value) == ('AAPL', '2026-09-11')


@pytest.mark.parametrize('value', [
    'Remember my previous question', {'ticker': 'AAPL'}, {'date': '2026-09-11'},
    {'ticker': 'AAPL', 'date': '2026-09-11', 'request': 'Neutral note'},
    {'ticker': 'AAPL', 'date': '2026-09-11', 'messages': []},
    {'ticker': '../outside', 'date': '2026-09-11'},
    {'ticker': ' AAPL', 'date': '2026-09-11'},
    {'ticker': 'AAPL', 'date': '20260911'},
    {'ticker': 'AAPL', 'date': '2026-02-30'},
    {'ticker': 'AAPL', 'date': None}, [],
])
def test_unsupported_input_is_rejected_before_any_native_work(value):
    graph = binding().TradingGraph()
    with pytest.raises(ValueError):
        graph.invoke(value)
    assert graph._native is None and graph._directory is None


def test_binding_calls_public_propagate_and_preserves_native_return(monkeypatch):
    from langchain_core.runnables.config import ensure_config
    module = binding()
    expected = {'market_report': 'Detailed evidence', 'final_trade_decision': 'Native final report'}
    calls = []
    callbacks = [object()]
    def propagate(ticker, date, *, asset_type):
        cfg = ensure_config({'recursion_limit': 100})  # Native get_graph_args sets only this.
        calls.append((ticker, date, asset_type, cfg))
        return expected, 'REVIEW'
    graph = module.TradingGraph()
    monkeypatch.setattr(graph, '_load_native', lambda settings: SimpleNamespace(propagate=propagate))
    result = graph.invoke({'ticker': 'AAPL', 'date': '2026-09-11'},
                          {'callbacks': callbacks, 'configurable': {'thread_id': 'case-one'}})
    assert result == {'final_state': expected, 'decision': 'REVIEW'}
    assert result['final_state'] is expected
    assert calls[0][:3] == ('AAPL', '2026-09-11', 'stock')
    assert calls[0][3]['callbacks'] == callbacks
    assert calls[0][3]['configurable']['thread_id'] == 'case-one'
    assert ensure_config()['callbacks'] is None


def test_profile_and_adapter_expose_text_encoded_native_task(tmp_path):
    from kuma import create_run
    from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
    config = LangGraphAdapterConfig.from_agent_dir(UNIT)
    assert config.input_key is None and config.output_key is None
    assert 'research_defaults' not in config.context
    seen = []
    def case_provider(context):
        seen.append(context)
        return {'case_id': 'native-task-profile', 'input_type': 'text', 'inputs': [
            {'input_id': 'step-1', 'payload_type': 'text',
             'payload': '{"ticker":"AAPL","date":"2026-09-11"}'}]}
    repo = tmp_path/'repo'
    repo.mkdir()
    run = create_run(repo_path=repo, agent_profile_path=UNIT/'requirement.md',
        case_provider=case_provider, judge=False, allow_local=True, track_files=False, max_steps=1)
    try:
        assert seen[0].input_type == 'text'
        assert binding().request_from_input(run.get_input()) == ('AAPL', '2026-09-11')
    finally:
        run.cancel()


# Run in an existing native Agent image with current binding mounted read-only.
# Only model completions, the market-data tool result and price/identity I/O are
# fixtures. The native graph, propagate, reflection, memory and logging are real.
NATIVE_LIFECYCLE_CHECK = r'''
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = ['/checks', '/opt/agent/agent']
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from trading import TradingGraph
import tradingagents.graph.trading_graph as upstream
import tradingagents.agents.analysts.market_analyst as market

class OfflineModel(BaseChatModel):
    @property
    def _llm_type(self):
        return 'offline-native-lifecycle'
    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=[t.name for t in tools])
    def with_structured_output(self, *args, **kwargs):
        raise NotImplementedError('Offline model uses native free-text fallback')
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if kwargs.get('tools') and not any(isinstance(m, ToolMessage) for m in messages):
            message = AIMessage(content='', tool_calls=[{'name': 'get_verified_market_snapshot',
                'args': {'symbol': 'AAPL', 'curr_date': '2025-01-01'},
                'id': 'offline-snapshot', 'type': 'tool_call'}])
        else:
            message = AIMessage(content='**Rating**: Hold\n\nNative fixture report and reflection.')
        return ChatResult(generations=[ChatGeneration(message=message)])

@tool
def snapshot(symbol: str, curr_date: str) -> str:
    """Return an offline market-data observation."""
    return 'AAPL fixture close=100; no external request'
snapshot.name = 'get_verified_market_snapshot'

class Capture(BaseCallbackHandler):
    def __init__(self):
        self.models, self.tools = 0, 0
    def on_chat_model_start(self, *args, **kwargs):
        self.models += 1
    def on_tool_start(self, *args, **kwargs):
        self.tools += 1

model = OfflineModel()
first, fresh = TradingGraph(), TradingGraph()
one, two, other = Capture(), Capture(), Capture()
with patch.object(upstream, 'create_llm_client', return_value=SimpleNamespace(get_llm=lambda: model)), \
     patch.object(upstream, 'get_verified_market_snapshot', snapshot), \
     patch.object(market, 'get_verified_market_snapshot', snapshot), \
     patch.object(upstream.TradingAgentsGraph, 'resolve_instrument_context', return_value='AAPL stock fixture'), \
     patch.object(upstream.TradingAgentsGraph, '_fetch_returns', return_value=(0.1, 0.05, 2, '2025-01-02')):
    try:
        a = first.invoke({'ticker': 'AAPL', 'date': '2025-01-01'},
                         {'callbacks': [one], 'configurable': {'thread_id': 'case-a'}})
        native = first._native
        directory = Path(first._directory.name)
        before = (one.models, one.tools)
        b = first.invoke({'ticker': 'AAPL', 'date': '2025-01-03'},
                         {'callbacks': [two], 'configurable': {'thread_id': 'case-a'}})
        c = fresh.invoke({'ticker': 'AAPL', 'date': '2025-01-03'},
                         {'callbacks': [other], 'configurable': {'thread_id': 'case-b'}})
        assert first._native is native
        assert a['decision'] == b['decision'] == c['decision'] == 'Hold'
        assert a['final_state']['past_context'] == ''
        assert 'Past analyses of AAPL' in b['final_state']['past_context']
        assert c['final_state']['past_context'] == ''
        assert native.curr_state is b['final_state']
        assert len(native.memory_log.load_entries()) == 2
        assert native.memory_log.load_entries()[0]['pending'] is False
        assert (directory/'memory.md').is_file()
        assert list((directory/'reports').rglob('*.json'))
        assert one.models > 0 and one.tools > 0 and two.models > 0 and two.tools > 0
        assert (one.models, one.tools) == before, 'Old callbacks must not leak into later Inputs'
        assert two.models > one.models, 'Second native call includes outcome reflection'
        result = {'status': 'passed', 'native_propagate': True, 'native_graph': True,
                  'native_memory_reflection': True, 'native_state_logging': True,
                  'case_isolation': True, 'per_input_callbacks': True,
                  'model_calls_observed': [one.models, two.models, other.models],
                  'tool_calls_observed': [one.tools, two.tools, other.tools],
                  'network': 'none', 'paid_calls': 0}
    finally:
        first.close()
        fresh.close()
assert not directory.exists()
print(json.dumps(result))
'''


@pytest.mark.skipif(not os.getenv('ABB_TRADING_NATIVE_IMAGE'), reason='Opt-in existing native Trading image')
def test_real_native_propagate_memory_callbacks_and_case_isolation():
    image = os.environ['ABB_TRADING_NATIVE_IMAGE']
    completed = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--user', '10001:10001',
        '--mount', f'type=bind,source={UNIT / "bindings"},target=/checks,readonly',
        '--entrypoint', 'python', image, '-c', NATIVE_LIFECYCLE_CHECK],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout[-1000:] + completed.stderr[-3000:]
    summary = json.loads(completed.stdout.strip().split('\n')[-1])
    assert summary['status'] == 'passed' and summary['native_memory_reflection'] is True
