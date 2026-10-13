"""Opt-in native import/packaging check; no inference or certification claim."""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path[:0] = ['/opt/agent/bindings', '/opt/agent/agent']
os.environ['OPENAI_API_KEY'] = 'offline-placeholder'
os.environ['OPENAI_COMPATIBLE_API_KEY'] = 'offline-placeholder'
assert os.getuid() != 0
from agentbench.adapter.langgraph import LangGraphAdapter
from kuma import create_run

agent_id = sys.argv[1]
if agent_id == 'tradingagents':
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    assert callable(TradingAgentsGraph.propagate)
elif agent_id == 'gpt-researcher':
    from multi_agents.agents import ChiefEditorAgent
    assert callable(ChiefEditorAgent.init_research_team)
else:
    raise ValueError(f'Unsupported packaging check: {agent_id}')
adapter = LangGraphAdapter.from_agent_dir('/opt/agent').load()
try:
    assert adapter.is_loaded
    with tempfile.TemporaryDirectory() as directory:
        run = create_run(repo_path=Path(directory), agent_profile_path=Path('/opt/agent/requirement.md'),
            case_provider=lambda _: {'case_id': 'offline-profile', 'input_type': 'text', 'inputs': [
                {'input_id': 'step-1', 'payload_type': 'text', 'payload': 'Offline packaging check'}]},
            judge=False, allow_local=True, track_files=False, max_steps=1)
        try:
            assert run.get_input() == 'Offline packaging check'
        finally:
            run.cancel()
finally:
    adapter.close()
print(json.dumps({'status': 'passed', 'network': 'none', 'agent_id': agent_id,
                  'native_import': True, 'binding_loaded': True, 'sdk_profile_loaded': True,
                  'native_execution': False, 'certification': False}))
