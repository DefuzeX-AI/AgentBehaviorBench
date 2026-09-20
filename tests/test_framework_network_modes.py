"""Framework defaults determine host preparation without a user mode switch."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent


def test_adapter_defaults():
    assert DEFAULT_ADAPTER_FACTORY.network_mode('acp') == 'observe'
    assert DEFAULT_ADAPTER_FACTORY.network_mode('langgraph') == 'replace'


@pytest.mark.parametrize('framework,mode',[('acp','observe'),('langgraph','replace')])
def test_manifest_infers_behavior_and_host_only_replaces_when_needed(tmp_path,framework,mode):
    (tmp_path/'agent.toml').write_text(f'''schema_version="defuzex-bench.agent.v2"
framework="{framework}"
[llm_interception]
trust_plugin="pem-env"
[[llm_interception.credentials]]
id="native"
agent_env="NATIVE_KEY"
auth_plugin="bearer-token"
[[llm_interception.routes]]
id="route"
host_patterns=["native.example"]
ports=[443]
methods=["POST"]
path_patterns=["/v1/chat/completions"]
protocol_plugin="openai-chat"
credential="native"
''')
    config=InterceptionConfig.from_agent_dir(tmp_path)
    assert config.mode==mode
    provider=Mock()
    provider.resolve.return_value=SimpleNamespace(provider_id='target',target_plugin='openrouter',
        base_url='https://target.example/v1',model='model',headers={},credential_env='TARGET_KEY')
    resolver=Mock();resolver.require.return_value='actual-target-secret'
    data,env=prepare_service_config(config,agent_id='a',max_trace_bytes=4096,secret_dir=tmp_path,
        secret_resolver=resolver,environ={'NATIVE_KEY':'real-native-secret'},model_provider=provider)
    assert data['mode']==mode
    if mode=='observe':
        provider.resolve.assert_not_called();resolver.require.assert_not_called()
        assert env=={'NATIVE_KEY':'real-native-secret'}
        assert 'target' not in data and data['credentials']==[]
        assert not (tmp_path/'target.secret').exists()
    else:
        provider.resolve.assert_called_once()
        assert env['NATIVE_KEY']!='real-native-secret'
        assert (tmp_path/'target.secret').read_text()=='actual-target-secret'


def test_observe_manifest_needs_no_replacement_credentials_or_target(tmp_path):
    (tmp_path/'agent.toml').write_text('''schema_version="defuzex-bench.agent.v2"
framework="acp"
[llm_interception]
trust_plugin="pem-env"
[[llm_interception.routes]]
id="native"
host_patterns=["native.example"]
methods=["POST"]
path_patterns=["/messages"]
protocol_plugin="anthropic-messages"
''')
    config=InterceptionConfig.from_agent_dir(tmp_path)
    assert config.mode=='observe' and config.credentials==()
    data,env=prepare_service_config(config,agent_id='a',max_trace_bytes=4096,secret_dir=tmp_path,
        secret_resolver=Mock(side_effect=AssertionError('secret')),environ={'ABB_MODEL_PROVIDER':'not-installed'})
    assert env=={} and 'target' not in data


def test_native_model_secrets_are_retained_by_acp_onboarding():
    from agentbench.onboarding.build_agent_env.build_toml.environment import runtime_environment
    interception={'credentials':[{'agent_env':'NATIVE_API_KEY'}]}
    assert runtime_environment([],[],interception,network_mode='observe')=={'secret_env_keys':['NATIVE_API_KEY']}
    assert runtime_environment([],[],interception,network_mode='replace')=={}


def test_observation_loss_is_not_a_successful_capture():
    state=InterceptionTraceState()
    state.emit(TraceEvent('llm_request',{'call_id':'call'}))
    state.emit(TraceEvent('llm_response',{'call_id':'call'}))
    state.emit(TraceEvent('observation_error',{'call_id':'call','error_code':'capture_failed'}))
    assert not state.wait_for_idle(timeout=.01,quiet=0)


def test_native_kuma_preflight_does_not_load_an_unused_replacement_provider(tmp_path):
    from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
    (tmp_path / 'requirement.md').write_text('profile')
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'preflight-placeholder',
                                         'ABB_MODEL_PROVIDER': 'not-installed'})
    assert runner.validate_sdk(SimpleNamespace(path=tmp_path, framework='acp')) == runner.provider_mode


def test_native_local_preflight_keeps_separate_judge_configuration(tmp_path):
    from agentbench.sdk.plugin.local.benchmark import LocalContainerRunner
    runner = LocalContainerRunner(environ={'ABB_MODEL_PROVIDER': 'not-installed',
        'ABB_LOCAL_JUDGE_BASE_URL': 'https://judge.example/v1',
        'ABB_LOCAL_JUDGE_MODEL': 'judge-model', 'ABB_LOCAL_JUDGE_API_KEY': 'test-judge-key'})
    assert runner.validate_sdk(SimpleNamespace(path=tmp_path, framework='acp')) == runner.provider_mode
