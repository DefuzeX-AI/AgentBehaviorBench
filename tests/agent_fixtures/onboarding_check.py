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
assert os.getuid() != 0
from kuma import create_run
from agentbench.adapter.langgraph import LangGraphAdapter

adapter = LangGraphAdapter.from_agent_dir('/opt/agent').load()
assert adapter.is_loaded
if agent_id == 'trading-agents':
    from copy import deepcopy
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    settings = tomllib.loads(Path('/opt/agent/agent.toml').read_text())['adapter']['context']
    with tempfile.TemporaryDirectory() as folder:
        cfg = deepcopy(DEFAULT_CONFIG)
        cfg.update(llm_provider=settings.get('provider', 'openai'),
                   backend_url='https://api.openai.com/v1', deep_think_llm='gpt-4.1-mini',
                   quick_think_llm='gpt-4.1-mini', data_cache_dir=folder+'/cache',
                   results_dir=folder+'/reports', memory_log_path=folder+'/memory.md')
        native = TradingAgentsGraph(selected_analysts=['market'], config=cfg)
        assert native.graph is not None
        assert native.quick_thinking_llm.use_responses_api is not True, 'Manifest routes require Chat Completions'
        state = native.propagator.create_initial_state('AAPL', '2026-09-11', past_context='Remember ONLY ALPHA')
        assert state['past_context'] == 'Remember ONLY ALPHA'
        details = {'native_graph_nodes': list(native.graph.nodes)}
elif agent_id == 'gpt-researcher':
    import torch
    import tiktoken
    from gpt_researcher import GPTResearcher
    native = GPTResearcher('Academic research', config_path='/opt/agent/bindings/research.json',
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
    details = {'native_retrievers': native.cfg.retrievers, 'embedding_dimensions':384,
               'torch':torch.__version__, 'offline_tokenizers':encodings}
else:
    raise ValueError(agent_id)
adapter.close()
print(json.dumps({'agent_id':agent_id,'network':'none','real_model_calls':0,
                  'kuma':importlib.metadata.version('kuma-defuzex'),'status':'passed',**details}))
