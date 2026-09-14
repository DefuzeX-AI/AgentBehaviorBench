"""Import and instantiate the actual downloaded Agent without network or real keys."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib

os.environ['OPENAI_API_KEY'] = 'offline-placeholder-not-a-credential'
os.environ['OPENAI_COMPATIBLE_API_KEY'] = 'offline-placeholder-not-a-credential'
sys.path[:0] = ['/opt/agent/bindings', '/opt/agent/agent']
agent_id = sys.argv[1]
manifest = tomllib.loads(Path('/opt/agent/agent.toml').read_text())
os.environ.update(manifest.get('llm_interception', {}).get('environment', {}))
assert os.getuid() != 0
from kuma import create_run
from agentbench.adapter.langgraph import LangGraphAdapter

adapter = LangGraphAdapter.from_agent_dir('/opt/agent').load()
assert adapter.is_loaded
if agent_id == 'trading-agents':
    from copy import deepcopy
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from yfinance._http import HAS_CURL_CFFI
    assert not HAS_CURL_CFFI, 'Transparent proxy requires the native requests backend'
    settings = manifest['adapter']['context']
    with tempfile.TemporaryDirectory() as folder:
        cfg = deepcopy(DEFAULT_CONFIG)
        cfg.update(llm_provider=settings.get('provider', 'openai'),
                   backend_url='https://api.openai.com/v1', deep_think_llm='gpt-4.1-mini',
                   quick_think_llm='gpt-4.1-mini', data_cache_dir=folder+'/cache',
                   results_dir=folder+'/reports', memory_log_path=folder+'/memory.md')
        native = TradingAgentsGraph(selected_analysts=['market'], config=cfg)
        assert native.graph is not None
        assert native.quick_thinking_llm.use_responses_api is not True, 'Manifest routes require Chat Completions'
        assert callable(native.propagate)
        state = native.propagator.create_initial_state('AAPL', '2026-09-11')
        assert not state.get('past_context')
        details = {'native_graph_nodes': list(native.graph.nodes)}
elif agent_id == 'gpt-researcher':
    import asyncio
    import torch
    import tiktoken
    from unittest.mock import patch
    from gpt_researcher import GPTResearcher
    from research import query_from_input
    current = 'Compare the clinical evidence for ALPHA'
    query = query_from_input({'query': current})
    assert query == current
    native = GPTResearcher(query,
                           config_path='/opt/agent/bindings/research.json',
                           verbose=False, mcp_strategy='disabled')
    assert native.cfg.retrievers == ['pubmed_central']
    assert native.cfg.embedding_provider == 'huggingface'
    vectors = native.memory.get_embeddings().embed_documents(['red apples', 'quantum mechanics'])
    assert len(vectors) == 2 and len(vectors[0]) == 384
    assert vectors[0] != vectors[1]
    assert torch.version.cuda is None
    encodings = ['cl100k_base', 'o200k_base', 'gpt2']
    for name in encodings:
        encoding = tiktoken.get_encoding(name)
        assert encoding.decode(encoding.encode('Biomedical evidence')) == 'Biomedical evidence'
    searched, selected, planned, written = [], [], [], []
    class OfflineSearch:
        requires_scraping = False
        def __init__(self, query, **kwargs):
            searched.append(query)
        def search(self, max_results=1):
            return []
    native.retrievers = [OfflineSearch]
    async def plan_completion(*args, **kwargs):
        planned.append(kwargs['messages'])
        return '["Clinical evidence for ALPHA"]'
    async def report_completion(*args, **kwargs):
        written.append(kwargs['messages'])
        return 'Offline native report'
    async def select_completion(*args, **kwargs):
        selected.append(kwargs['messages'])
        return '{"server":"Researcher","agent_role_prompt":"Research public literature"}'
    async def delegated_research():
        return []
    async def verify_native_context_hooks():
        with patch('gpt_researcher.actions.agent_creator.create_chat_completion', select_completion), \
             patch.object(native.research_conductor, 'conduct_research', delegated_research):
            await native.conduct_research()
        with patch('gpt_researcher.actions.query_processing.create_chat_completion', plan_completion):
            queries = await native.research_conductor.plan_research(native.query)
        assert queries == ['Clinical evidence for ALPHA']
        native.context = 'Offline article fixture: https://example.org/article'
        with patch('gpt_researcher.actions.report_generation.create_chat_completion', report_completion):
            assert await native.write_report() == 'Offline native report'
    asyncio.run(verify_native_context_hooks())
    assert searched == [current]
    assert current in selected[0][-1]['content']
    assert current in planned[0][-1]['content']
    assert current in written[0][-1]['content']
    assert native.query == current and 'prompt_family' not in native.kwargs
    details = {'native_retrievers': native.cfg.retrievers, 'embedding_dimensions':384,
               'torch':torch.__version__, 'offline_tokenizers':encodings,
               'native_current_input_paths':['agent_selection','planning','writing'],
               'native_entrypoint_checked':True}
else:
    raise ValueError(agent_id)
adapter.close()
print(json.dumps({'agent_id':agent_id,'network':'none','real_model_calls':0,
                  'kuma':importlib.metadata.version('kuma-defuzex'),'status':'passed',**details}))
