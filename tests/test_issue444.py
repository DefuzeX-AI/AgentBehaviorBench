"""Issue #444: the upstream model timeout reaches the interceptor configuration."""
from types import SimpleNamespace
import pytest

from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.interception.config import CredentialConfig
from agentbench.runtime.interception.service_config import prepare_service_config, upstream_timeout_seconds


def _prepare(tmp_path, **extra):
    env = dict(OPENROUTER_MODEL='selected-model', OPENROUTER_API_KEY='test-secret', **extra)
    config = SimpleNamespace(mode='replace', observation_headers={}, observation_tool_purposes={},
                             routes=(), tool_routes=(), token_counting={},
                             credentials=(CredentialConfig('openai', 'OPENAI_API_KEY', 'bearer-token'),))
    return prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096, secret_dir=tmp_path,
                                  secret_resolver=EnvironmentSecretResolver(env), environ=env)[0]


def test_default_and_override_are_written_for_replace_mode(tmp_path):
    assert _prepare(tmp_path)['upstream_timeout_seconds'] == 300.0
    assert _prepare(tmp_path, ABB_MODEL_UPSTREAM_TIMEOUT_SEC='45')['upstream_timeout_seconds'] == 45.0


@pytest.mark.parametrize('value', ['0', '-5', 'nan', 'inf', 'soon', ''])
def test_invalid_values_are_rejected(value):
    with pytest.raises(ValueError, match='ABB_MODEL_UPSTREAM_TIMEOUT_SEC'):
        upstream_timeout_seconds({'ABB_MODEL_UPSTREAM_TIMEOUT_SEC': value})
