"""Issue #83: model target routing and zero-model-call trace acceptance."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.contracts.execution import RunControl, RunCancelled, RuntimeInfrastructureError
from agentbench.runtime.docker.runtime import DockerRuntime, DockerRuntimeError
from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent
from agentbench.runtime.interception.config import CredentialConfig, InterceptionConfig
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.interception.target_routing import resolve_target_routing
from agentbench.runtime.interception.config import InterceptionConfigurationError


def test_default_target_handles_text_and_images_without_a_routing_file(tmp_path):
    env = dict(OPENROUTER_MODEL='selected-model', OPENROUTER_API_KEY='test-secret')
    plan = resolve_target_routing(env)
    assert not plan.explicit
    assert plan.targets['default'].model == 'selected-model'
    assert plan.inputs['default'] == ('text', 'image')
    config = SimpleNamespace(mode='replace', observation_headers={}, observation_tool_purposes={},
                             routes=(), tool_routes=(), token_counting={},
                             credentials=(CredentialConfig('openai', 'OPENAI_API_KEY', 'bearer-token'),))
    data, tokens = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=EnvironmentSecretResolver(env), environ=env)
    assert data['target']['input_modalities'] == ['text', 'image']
    assert data['target']['model'] == 'selected-model'
    assert 'targets' not in data and 'target_rules' not in data
    assert tokens['OPENAI_API_KEY'] != env['OPENROUTER_API_KEY']


def test_prepare_multiple_model_targets(tmp_path):
    routing = tmp_path / 'models.toml'
    routing.write_text('''
[targets.chat]
provider = "glm"
model = "configured-chat"

[targets.vectors]
provider = "glm"
model = "configured-vector"
credential_env = "VECTOR_SERVICE_KEY"
base_url = "https://vectors.example/api"
[targets.vectors.endpoint_paths]
"/embeddings" = "/embeddings"

[[rules]]
id = "chat"
protocols = ["openai-chat"]
input = "text"
target = "chat"

[[rules]]
id = "vectors"
protocols = ["openai-embeddings"]
input = "text"
target = "vectors"
''')
    env = dict(ABB_MODEL_ROUTING_CONFIG=str(routing), GLM_API_KEY='chat-secret',
               VECTOR_SERVICE_KEY='vector-secret')
    config = SimpleNamespace(mode='replace', observation_headers={}, observation_tool_purposes={},
                             routes=(), tool_routes=(), token_counting={},
                             credentials=(CredentialConfig('openai', 'OPENAI_API_KEY', 'bearer-token'),))
    data, agent_env = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=EnvironmentSecretResolver(env), environ=env)
    assert data['targets']['vectors']['model'] == 'configured-vector'
    assert data['targets']['chat']['model'] == 'configured-chat'
    for name, secret in [('chat', 'chat-secret'), ('vectors', 'vector-secret')]:
        assert (tmp_path / Path(data['targets'][name]['secret_file']).name).read_text() == secret
        assert secret not in json.dumps(data)
        assert secret not in json.dumps(agent_env)
    assert 'secret_file' not in data['credentials'][0]
    assert set(agent_env) == {'OPENAI_API_KEY'}


@pytest.mark.parametrize('rule, message', [
    ('target = "absent"', 'unknown target'),
    ('input = "image"', 'does not declare image'),
])
def test_routing_rejects_invalid_references_before_startup(tmp_path, rule, message):
    text = '''[targets.chat]
provider = "openrouter"
model = "test/model"
[[rules]]
id = "chat"
target = "chat"
input = "text"
protocols = ["openai-chat"]
'''
    before = 'target = "chat"' if rule.startswith('target') else 'input = "text"'
    path = tmp_path / 'models.toml'
    path.write_text(text.replace(before, rule))
    with pytest.raises(InterceptionConfigurationError, match=message):
        resolve_target_routing({'ABB_MODEL_ROUTING_CONFIG': str(path)})


def test_observe_ignores_replacement_targets_and_secrets(tmp_path):
    config = SimpleNamespace(mode='observe', observation_headers={}, observation_tool_purposes={},
                             routes=(), tool_routes=(), token_counting={}, credentials=())
    data, env = prepare_service_config(config, agent_id='native', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=None, environ={'ABB_MODEL_ROUTING_CONFIG': 'missing-file'})
    assert 'targets' not in data and 'target' not in data
    assert env == {}


def test_run_target_and_explicit_models_have_distinct_precedence(tmp_path):
    path = tmp_path / 'models.toml'
    path.write_text('''[targets.chat]
use_run_target = true
[targets.vectors]
provider = "openrouter"
model = "configured-vector-model"
[[rules]]
id = "chat"
target = "chat"
input = "text"
protocols = ["openai-chat"]
[[rules]]
id = "vectors"
target = "vectors"
input = "text"
protocols = ["openai-embeddings"]
''')
    plan = resolve_target_routing({'ABB_MODEL_ROUTING_CONFIG': str(path), 'ABB_MODEL': 'run-model'})
    assert plan.targets['chat'].model == 'run-model'
    assert plan.targets['vectors'].model == 'configured-vector-model'


@pytest.mark.parametrize('field, value', [('base_url', '"https://user:password@example.com"'),
    ('endpoint_paths', '{"/embeddings" = "//elsewhere"}'),
    ('endpoint_paths', '[]'), ('use_run_target', '"yes"')])
def test_invalid_target_configuration_is_rejected(tmp_path, field, value):
    path = tmp_path / 'models.toml'
    path.write_text(f'''[targets.model]
provider = "openrouter"
model = "test-model"
{field} = {value}
[[rules]]
id = "rule"
target = "model"
input = "text"
protocols = ["openai-chat"]
''')
    with pytest.raises(InterceptionConfigurationError):
        resolve_target_routing({'ABB_MODEL_ROUTING_CONFIG': str(path)})


# F13: model calls are optional; evidence integrity is not.
def validator(state, monkeypatch, *, control=None):
    # Exercise the real drain/check logic without waiting two seconds per failure.
    wait = state.wait_for_idle
    monkeypatch.setattr(state, 'wait_for_idle', lambda **kw: wait(timeout=.02, quiet=0, **kw))
    runtime = SimpleNamespace(control=control or RunControl())
    return DockerRuntime._trace_validation_callback(runtime, state)


def emit(state, name, **data):
    state.emit(TraceEvent(name, {'call_id': 'call', **data}))


def test_deterministic_graph_has_execution_evidence_without_model_calls(monkeypatch):
    from langgraph.graph import StateGraph, START, END
    from agentbench.observe.langchain import TraceCallback

    events = []
    store = SimpleNamespace(record=lambda event, **data: events.append(event))
    graph = StateGraph(dict)
    graph.add_node('fixed', lambda state: {'answer': 'fixed response'})
    graph.add_edge(START, 'fixed')
    graph.add_edge('fixed', END)
    output = graph.compile().invoke({}, {'callbacks': [TraceCallback(store)]})

    assert output == {'answer': 'fixed response'}
    assert 'span_start' in events and 'span_end' in events
    state = InterceptionTraceState()
    validator(state, monkeypatch)(state.checkpoint())
    assert 'requests=0, responses=0' in state.diagnostic()


def test_tool_only_execution_is_accepted(monkeypatch):
    state = InterceptionTraceState()
    emit(state, 'tool_request', required=True)
    emit(state, 'tool_response', status=200)
    validator(state, monkeypatch)(0)


def test_later_turn_need_not_make_another_model_call(monkeypatch):
    state = InterceptionTraceState()
    emit(state, 'llm_request')
    emit(state, 'llm_response')
    validator(state, monkeypatch)(state.checkpoint())


@pytest.mark.parametrize('failure', ['unfinished', 'authentication_failed', 'capture_failed', 'truncated'])
def test_zero_call_acceptance_does_not_accept_lost_evidence(monkeypatch, failure):
    state = InterceptionTraceState()
    if failure == 'unfinished':
        emit(state, 'llm_request')
    elif failure == 'authentication_failed':
        emit(state, 'llm_error', error_code=failure)
    elif failure == 'capture_failed':
        emit(state, 'observation_error')
    else:
        emit(state, 'llm_request')
        emit(state, 'llm_response', truncated=True)
    with pytest.raises(DockerRuntimeError, match='Model trace is incomplete'):
        validator(state, monkeypatch)(0)


def test_zero_calls_do_not_hide_trace_write_failure(monkeypatch):
    state = InterceptionTraceState()
    state.fail(OSError('evidence disk unavailable'))
    with pytest.raises(RuntimeInfrastructureError, match='evidence disk'):
        validator(state, monkeypatch)(0)


def test_zero_calls_still_honor_cancellation(monkeypatch):
    control = RunControl()
    control.cancel()
    with pytest.raises(RunCancelled):
        validator(InterceptionTraceState(), monkeypatch, control=control)(0)


@pytest.mark.parametrize('legacy', ['', 'required = true\n', 'required = false\n'])
def test_legacy_required_flag_no_longer_controls_interception(tmp_path, legacy):
    (tmp_path / 'agent.toml').write_text(
        'schema_version="defuzex-bench.agent.v2"\nframework="acp"\n'
        '[llm_interception]\n' + legacy + 'trust_plugin="pem-env"\n')
    config = InterceptionConfig.from_agent_dir(tmp_path)
    assert config is not None and config.mode == 'observe'
    assert not hasattr(config, 'required')
