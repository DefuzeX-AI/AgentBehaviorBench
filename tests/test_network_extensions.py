"""Agent-owned rules and auxiliary evidence do not weaken the network policy."""
import pytest
from agentbench.runtime.interception.network_rules import load_network_rules
from agentbench.runtime.interception.trace import TraceEvent, InterceptionTraceState
from agentbench.runtime.interception.config import InterceptionConfig, InterceptionConfigurationError


def send(state, event, call='call', **data):
    state.emit(TraceEvent(event, dict(call_id=call, **data)))


def test_auxiliary_calls_never_count_as_model_generation_and_must_finish():
    state = InterceptionTraceState()
    send(state, 'model_auxiliary_request')
    assert not state.wait_for_idle(timeout=.002, quiet=0)
    send(state, 'model_auxiliary_response', status=404)
    assert state.wait_for_idle(timeout=.02, quiet=0)
    assert state.checkpoint() == 0
    assert not state.wait_for_completion_after(0, timeout=0)
    send(state, 'llm_request', 'real')
    send(state, 'llm_response', 'real')
    assert state.wait_for_completion_after(0, timeout=0)


@pytest.mark.parametrize('event,data', [('tool_response', {'status': 403}),
                                       ('tool_error', {'error_code': 'transport_error'})])
def test_required_network_failure_is_not_misreported_as_capture_loss(event, data):
    state = InterceptionTraceState()
    send(state, 'tool_request', required=True, purpose='content_safety')
    send(state, event, **data)
    assert not state.wait_for_idle(timeout=.02, quiet=0)
    assert 'capture_rejected=False' in state.diagnostic()
    assert 'operation_failure=' in state.diagnostic()


def test_required_network_rejection_body_is_preserved_as_agent_behavior():
    state = InterceptionTraceState()
    send(state, 'tool_request', required=True, purpose='content_safety')
    assert not state.wait_for_idle(timeout=.002, quiet=0)
    send(state, 'tool_response', status=200, payload={'pass': False})
    assert state.wait_for_idle(timeout=.02, quiet=0)


def test_optional_metadata_failure_is_terminal_evidence_not_fatal():
    state = InterceptionTraceState()
    send(state, 'tool_request', required=False, purpose='metadata')
    send(state, 'tool_response', status=503)
    assert state.wait_for_idle(timeout=.02, quiet=0)


def test_undeclared_requests_are_recorded_without_rejecting_completed_generation():
    state = InterceptionTraceState()
    send(state, 'llm_request')
    send(state, 'llm_response')
    send(state, 'llm_error', 'unknown', error_code='egress_denied')
    assert state.wait_for_idle(timeout=.02, quiet=0)
    assert 'egress_denied=1' in state.diagnostic()


def test_trace_persistence_failure_still_works():
    state = InterceptionTraceState()
    state.fail(OSError('disk'))
    with pytest.raises(RuntimeError, match='persistence failed'):
        state.check_persistence()


def test_network_file_must_be_declared_contained_and_versioned(tmp_path):
    outer = tmp_path / 'outside.toml'
    outer.write_text('schema_version="abb.network.v1"')
    root = tmp_path / 'unit'
    root.mkdir()
    (root / 'link.toml').symlink_to(outer)
    for name in ('../outside.toml', str(outer), 'link.toml'):
        with pytest.raises(ValueError, match='inside'):
            load_network_rules(root, name)
    assert load_network_rules(root, None) == {}
    (root / 'rules.toml').write_text('schema_version="abb.network.v1"\nunknown=true')
    with pytest.raises(ValueError, match='Unknown'):
        load_network_rules(root, 'rules.toml')


def test_network_rules_merge_with_existing_sdk_tool_routes(tmp_path):
    (tmp_path / 'agent.toml').write_text('''schema_version="defuzex-bench.agent.v2"
[llm_interception]
trust_plugin="pem-env"
network_config="rules.toml"
[[llm_interception.credentials]]
id="model"
agent_env="API_KEY"
auth_plugin="bearer-token"
[[llm_interception.tool_routes]]
host_patterns=["sdk.example"]
methods=["POST"]
path_patterns=["/generate"]
purpose="evaluation"
''')
    (tmp_path / 'rules.toml').write_text('''schema_version="abb.network.v1"
[token_counting]
mode="local_estimate"
[token_counting.models]
"test/model"="o200k_base"
[[tool_routes]]
host_patterns=["native.example"]
methods=["POST"]
path_patterns=["/review"]
purpose="content_safety"
required=true
''')
    config = InterceptionConfig.from_agent_dir(tmp_path)
    assert [r.purpose for r in config.tool_routes] == ['evaluation', 'content_safety']
    assert config.tool_routes[-1].required is True
    assert config.token_counting['models']['test/model'] == 'o200k_base'
    text = (tmp_path / 'rules.toml').read_text().replace('["native.example"]', '["*"]')
    (tmp_path / 'rules.toml').write_text(text)
    with pytest.raises(InterceptionConfigurationError):
        InterceptionConfig.from_agent_dir(tmp_path)


def test_runtime_distinguishes_required_operation_failure_from_incomplete_trace():
    from agentbench.runtime.docker.runtime import DockerRuntime, DockerRuntimeError
    from agentbench.runtime.contracts.execution import RunControl
    from types import SimpleNamespace
    state = InterceptionTraceState()
    send(state, 'llm_request', 'model')
    send(state, 'llm_response', 'model')
    send(state, 'tool_request', 'native', required=True)
    send(state, 'tool_response', 'native', status=401)
    runtime = SimpleNamespace(control=RunControl())
    check = DockerRuntime._required_trace_callback(runtime, state)
    with pytest.raises(DockerRuntimeError, match='Required Agent network operation failed'):
        check(0)


def test_onboarding_stages_referenced_rules_without_executing_agent_code(tmp_path):
    from types import SimpleNamespace
    from agentbench.onboarding.build_agent_env.build_toml.validation import validate_manifest
    root = tmp_path / 'unit'
    (root / 'network').mkdir(parents=True)
    (root / 'network/rules.toml').write_text('''schema_version="abb.network.v1"
[[tool_routes]]
host_patterns=["native.example"]
methods=["POST"]
path_patterns=["/review"]
purpose="content_safety"
required=true
''')
    manifest = '''schema_version="defuzex-bench.agent.v2"
agent_id="native-cli"
framework="acp"
[runtime]
type="docker"
execution="oneshot"
secret_env_keys=["NATIVE_ACCESS_TOKEN"]
[build]
context="."
dockerfile="Dockerfile"
[launch]
argv=["python", "-m", "agentbench.runtime.agentcontainer.worker"]
[adapter]
type="acp"
command=["node", "/opt/agent/agent/cli.js"]
cwd="/workspace"
[llm_interception]
trust_plugin="pem-env"
network_config="network/rules.toml"
[[llm_interception.credentials]]
id="model"
agent_env="API_KEY"
auth_plugin="bearer-token"
'''
    session = SimpleNamespace(source=SimpleNamespace(directory=root), agent_id='native-cli', plan={})
    validate_manifest(manifest, session)
    assert not (root / 'Dockerfile').exists()
