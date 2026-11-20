"""Native defaults, explicit overrides and observation context at real binding boundaries."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType

import pytest

ROOT = Path(os.environ.get('ABB_BINDING_ROOT', Path(__file__).resolve().parents[1]))


def load(unit, filename='bridge.py'):
    path = ROOT / 'resources/agents' / unit / 'bindings' / filename
    spec = spec_from_file_location('binding_' + unit.replace('-', '_'), path)
    mod = module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def modules(monkeypatch, **entries):
    for name, values in entries.items():
        mod = ModuleType(name)
        mod.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, mod)


@pytest.fixture
def config():
    callbacks = pytest.importorskip("langchain_core.callbacks", reason="Run binding tests in the ABB LangChain environment")
    callback = callbacks.BaseCallbackHandler()
    return {'recursion_limit': 731, 'callbacks': [callback], 'tags': ['test'],
            'metadata': {'source': 'test'}, 'configurable': {'thread_id': 'thread'}}


@pytest.mark.parametrize('override', [False, True])
def test_labscript_native_attempts_and_run_config(monkeypatch, config, override):
    calls = []
    async def invoke(state, config=None):
        calls.append((state, config))
        return {'python_code': 'pass', 'final_outcome': 'done'}
    def native_stream(query, max_attempts=7):
        pass
    modules(monkeypatch, **{
        'backend.pylabrobot_agent': dict(create_pylabrobot_agent=lambda: SimpleNamespace(ainvoke=invoke),
            generate_dynamic_pylabrobot_knowledge=lambda _: 'knowledge',
            run_pylabrobot_agent_and_stream_events=native_stream),
        'backend.pylabrobot_utils': dict(load_hardware_configuration=lambda: {})})
    supplied = config if override else {}
    if override: supplied['configurable']['max_attempts'] = 11
    graph = load('03-labscript-ai').create_graph()
    graph.invoke({'message': 'protocol'}, config=supplied)
    state, forwarded = calls[0]
    assert state['max_attempts'] == (11 if override else 7)
    assert forwarded['recursion_limit'] == (731 if override else 100)
    if override:
        assert forwarded['callbacks'] is config['callbacks']
        assert forwarded['metadata'] is config['metadata']
        assert forwarded['configurable'] is config['configurable']
    assert 'recursion_limit' not in supplied if not override else supplied['recursion_limit'] == 731


@pytest.mark.parametrize('override', [False, True])
def test_evoscientist_reads_effective_native_limit(monkeypatch, config, override):
    modules(monkeypatch, **{'EvoScientist.cli._constants':dict(build_metadata=lambda *a: {})})
    cls = load('36-evoscientist').EvoScientistGraph
    graph = cls.__new__(cls)
    graph._workspace = 'workspace'
    graph._config = SimpleNamespace(recursion_limit=9021, model='native')
    forwarded = graph._run_config(config if override else {})
    assert forwarded['recursion_limit'] == (731 if override else 9021)
    if override:
        assert forwarded['callbacks'] is config['callbacks']
        assert forwarded['configurable']['thread_id'] == 'thread'
        assert 'hitl_suppressed' not in config['configurable']


def test_local_deep_research_native_settings_and_explicit_snapshot(monkeypatch, config):
    seen=[]
    def snapshot(overrides):
        seen.append(overrides)
        return {'native_budget': 99, **overrides}
    def summary(query, **kwargs):
        assert kwargs['settings_snapshot']['native_budget'] == 99
        return {'summary': 'done'}
    modules(monkeypatch, **{'local_deep_research.api':dict(quick_summary=summary),
        'local_deep_research.api.settings_utils':dict(create_settings_snapshot=snapshot)})
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    graph=load('32-local-deep-research','ldr_bridge.py').create_graph()
    graph.invoke({'query':'research'}, config=config)
    assert not any(k.endswith(('max_iterations','max_sub_iterations','max_results','max_subagent_workers')) for k in seen[-1])
    config['configurable']['settings_snapshot']={'langgraph_agent.max_iterations': 123}
    graph.invoke({'query':'research'},config=config)
    assert seen[-1]['langgraph_agent.max_iterations']==123


@pytest.mark.parametrize('override',[False,True])
def test_air_scenario_owns_limit_unless_explicit(monkeypatch,config,override):
    mod=load('46-air-lingjing');seen=[]
    async def invoke(value,config=None):
        seen.append((value,config));return {}
    graph=mod.AgentGraph.__new__(mod.AgentGraph)
    graph._builder=lambda:SimpleNamespace(ainvoke=invoke)
    monkeypatch.setattr(mod,'_scenario',lambda _: {'termination':{'max_steps':87}})
    monkeypatch.delenv('LINGJING_MAX_STEPS',raising=False)
    if override:config['configurable']['max_steps']=233
    graph.invoke('mission',config=config)
    state,forwarded=seen[0]
    assert forwarded is config
    assert state['max_steps']==233 if override else 'max_steps' not in state


def test_hunt_request_uses_native_validation_and_defaults(monkeypatch):
    from pydantic import BaseModel,Field
    class Request(BaseModel):
        description:str=''
        website_url:str=''
        product_keywords:list[str]=Field(default_factory=list)
        max_rounds:int=Field(default=19,ge=1,le=50)
    modules(monkeypatch, **{'api.routes':dict(HuntRequest=Request)})
    mod=load('60-ai-find-customer')
    assert mod.hunt_request_from_input('research')['max_rounds']==19
    assert mod.hunt_request_from_input({'description':'research','max_rounds':34})['max_rounds']==34
    with pytest.raises(ValueError):mod.hunt_request_from_input({'description':'research','max_rounds':51})


def test_tsci_leaves_native_models_and_work_size_unchanged(monkeypatch):
    mod=load('50-timeseriesscientist','tsci_workflow.py')
    defaults={'num_slices':10,'input_length':50,'horizon':12,'k_models':30,'llm_model':'native','debug':False,'env_vars':{'secret':'not for prompts'}}
    modules(monkeypatch,**{'config.default_config':dict(DEFAULT_CONFIG=defaults)})
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    for name in ('NUM_SLICES','INPUT_LENGTH','HORIZON','K_MODELS'):monkeypatch.delenv('TSCI_DEPLOY_'+name,raising=False)
    monkeypatch.setattr(mod,'_resolve_data_path',lambda:'dataset.csv')
    calls=[]
    class Client:
        max_tokens=8100
        max_retries=4
        request_timeout=130
        def invoke(self,value):calls.append(value);return value
    client=Client()
    class Native:
        def __init__(self,**kwargs):
            for name in ('preprocess_agent','analysis_agent','validation_agent','forecast_agent','report_agent'):
                setattr(self,name,SimpleNamespace(llm=client,tools=SimpleNamespace(llm=client)))
    monkeypatch.setattr(mod,'_deployment_graph_class',lambda:Native)
    graph=mod.TimeSeriesScientistWorkflow()
    try:
        cfg=graph._build_config({})
        assert cfg['num_slices']==10 and cfg['k_models']==30
        assert 'env_vars' not in cfg and 'env_vars' in defaults
        native=graph._load_native(cfg)
        assert native.analysis_agent.llm is client
        for _ in range(120):native.analysis_agent.llm.invoke('x'*60001)
        assert len(calls)==120
        assert (client.max_tokens,client.max_retries,client.request_timeout)==(8100,4,130)
        assert graph._build_config({'num_slices':77})['num_slices']==77
        assert mod.request_from_input({'num_slices':77})[1]['num_slices']==77
    finally:graph.close()


def test_csgo_does_not_truncate_native_item_list(monkeypatch):
    mod=load('54-csgotrading')
    monkeypatch.setattr(mod,'_snapshot_dates',lambda:['2026-01-01'])
    cls=next(c for c in vars(mod).values() if isinstance(c,type) and hasattr(c,'_parse'))
    graph=cls.__new__(cls);graph._configured_items=[f'item-{i}' for i in range(12)]
    assert graph._parse('analyse portfolio')[1]==graph._configured_items
    assert graph._parse(', '.join(graph._configured_items))[1]==graph._configured_items
    summary=graph._summary('2026-01-01','config',{'id':1,'cashflow':1.0,'total_assets':2.0,'positions':[]},[],0.1)
    assert '12 configured' in summary

@pytest.mark.parametrize('override',[False,True])
def test_lambchat_preserves_explicit_limit_and_native_default(monkeypatch,config,override):
    mod=load('84-lambchat');seen=[]
    async def invoke(value,config=None):seen.append(config);return {'output':'done'}
    native=SimpleNamespace(_initialized=True,recursion_limit=492,_graph=SimpleNamespace(ainvoke=invoke))
    graph=mod._LambChatQuickAgent.__new__(mod._LambChatQuickAgent)
    graph._thread=0
    monkeypatch.setattr(graph,'_ensure_agent',lambda:native)
    monkeypatch.setattr(mod,'_model_config',lambda:{})
    supplied=config if override else {'configurable':{'thread_id':'native-thread'}}
    graph.invoke('hello',config=supplied)
    assert seen[0]['recursion_limit']==(731 if override else 492)
    assert seen[0]['configurable']['thread_id']==supplied['configurable']['thread_id']
    if override:assert seen[0]['callbacks'] is supplied['callbacks']
    assert 'agent_options' not in supplied['configurable']

@pytest.mark.parametrize('override',[False,True])
def test_rag_reads_native_configuration(monkeypatch,config,override):
    seen=[]
    class Configuration:
        @classmethod
        def from_runnable_config(cls, supplied):return SimpleNamespace(max_search_queries=41)
    modules(monkeypatch,**{'assistant.configuration':dict(Configuration=Configuration)})
    def invoke(value,supplied):seen.append(supplied);return {'final_answer':'done'}
    graph=load('45-local-rag-researcher-deepseek').LocalRagResearcherGraph(SimpleNamespace(invoke=invoke))
    if override:config['configurable']['max_search_queries']=55
    graph.invoke('question',config=config)
    assert seen[0]['configurable']['max_search_queries']==(55 if override else 41)
    assert seen[0]['callbacks'] is config['callbacks']
    assert 'enable_web_search' not in config['configurable']

@pytest.mark.parametrize('override',[False,True])
def test_deerflow_delegates_default_and_forwards_explicit_context(monkeypatch,config,override):
    import threading
    seen=[]
    from langchain_core.runnables.config import var_child_runnable_config
    def chat(message,**kwargs):seen.append((kwargs,var_child_runnable_config.get()));return 'done'
    modules(monkeypatch, **{'runtime_config':dict(prepare_runtime_config=lambda:None)})
    mod=load('01-deer-flow','deerflow_client.py')
    cls=next(c for c in vars(mod).values() if isinstance(c,type) and hasattr(c,'invoke'))
    graph=cls.__new__(cls)
    graph._lock=threading.Lock();graph._closed=False;graph._thread_id='native-thread'
    monkeypatch.setattr(graph,'_load',lambda:SimpleNamespace(chat=chat))
    supplied=config if override else {}
    graph.invoke('hello',config=supplied)
    kwargs,ambient=seen[0]
    assert kwargs['recursion_limit']==731 if override else 'recursion_limit' not in kwargs
    assert kwargs['thread_id']==('thread' if override else 'native-thread')
    if override:assert ambient['callbacks'] is config['callbacks']

@pytest.mark.parametrize('limit',[None,64])
def test_grapharc_native_constructor_and_call_context(monkeypatch,tmp_path,config,limit):
    from langchain_core.runnables.config import var_child_runnable_config
    seen=[]
    class Native:
        def __init__(self,*a,max_iterations=8,**kw):self.max_iterations=max_iterations
        def run(self,prompt):
            seen.append((self.max_iterations,var_child_runnable_config.get()))
            return SimpleNamespace(output='done')
    dummy=lambda *a,**kw:SimpleNamespace()
    modules(monkeypatch,**{
        'grapharc.tools.core':dict(register_core_tools=dummy),
        'grapharc.harness':dict(ToolRegistry=dummy,Harness=dummy,LocalExecutor=dummy),
        'grapharc.harness.agent':dict(AgentNode=Native),
        'grapharc.harness.permissions':dict(PermissionPolicy=dummy,PermissionRule=dummy,Decision=SimpleNamespace(ALLOW='allow')),
        'grapharc.gateway':dict(get_model=dummy)})
    graph=load('96-grapharc').GraphARCGraph(workspace_path=str(tmp_path))
    if limit is not None:config['configurable']['max_iterations']=limit
    assert graph.invoke('hello',config=config)=='done'
    assert seen[0][0]==(8 if limit is None else limit)
    assert seen[0][1]['callbacks'] is config['callbacks']
    assert graph.agent.max_iterations==8

@pytest.mark.parametrize('override',[False,True])
def test_mini_opencode_keeps_native_limit_and_caller_thread(config,override):
    supplied=config if override else {}
    forwarded=load('69-mini-opencode')._run_config(supplied,'native-thread')
    assert forwarded['recursion_limit']==(731 if override else 100)
    assert forwarded['configurable']['thread_id']==('thread' if override else 'native-thread')
    if override:assert forwarded['callbacks'] is supplied['callbacks']
    else:assert supplied=={}


@pytest.mark.parametrize('override',[False,True])
def test_multi_agent_cad_keeps_native_cli_limit_and_initial_state(monkeypatch,config,override):
    seen=[]
    def invoke(state,forwarded):seen.append((state,forwarded));return {}
    modules(monkeypatch,**{'multi_agent_cad.graph':dict(
        build_graph=lambda:SimpleNamespace(invoke=invoke),
        get_default_initial_state=lambda **kwargs:{'max_iterations':9})})
    graph=load('04-multi-agent-cad').create_graph()
    graph.invoke('design',config=config if override else {})
    state,forwarded=seen[0]
    assert state['max_iterations']==9
    assert forwarded['recursion_limit']==(731 if override else 50)
    if override:assert forwarded['callbacks'] is config['callbacks']
