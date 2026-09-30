"""Run-level target configuration must keep separate credentials out of Agent env."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.interception.config import CredentialConfig
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.interception.target_routing import resolve_target_routing
from agentbench.runtime.interception.config import InterceptionConfigurationError


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
