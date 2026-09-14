"""Service-backed Agents must retain their native environment in SDK overlays."""

from types import SimpleNamespace
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest

from agentbench.sdk.plugin.kuma.image import evaluation_agent
from agentbench.sdk.plugin.kuma.manifest import extend_runtime_environment


@pytest.mark.parametrize('runtime', [
    '[runtime]\ntype = "docker"\n',
    '[runtime]\ntype = "docker"\nenv_keys = ["DATABASE_HOST"]\n',
    '["runtime"] # service configuration\ntype = "docker"\n"env_keys" = [\n'
    '  "DATABASE_HOST", # native DB\n  "KUMA_API_KEY",\n]\n',
])
def test_overlay_preserves_native_environment_and_other_tables(tmp_path, runtime):
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'Dockerfile').write_text('FROM python:3.13-slim\nUSER agent\n')
    source = ('agent_id = "service-agent"\n' + runtime +
              'secret_env_keys = ["DATABASE_PASSWORD"]\n'
              '[launch]\nargv = ["python", "native.py"]\n'
              '[other]\nenv_keys = ["KEEP_ME"]\n')
    manifest = root / 'agent.toml'
    manifest.write_text(source)
    with evaluation_agent(SimpleNamespace(path=root, agent_id='service-agent', framework='langgraph')) as staged:
        parsed = tomllib.loads((staged.path / 'agent.toml').read_text())
        keys = parsed['runtime']['env_keys']
        assert keys.count('KUMA_API_KEY') == keys.count('DEFUZEX_API_KEY') == 1
        if 'DATABASE_HOST' in source:
            assert 'DATABASE_HOST' in keys
        assert parsed['runtime']['secret_env_keys'] == ['DATABASE_PASSWORD']
        assert parsed['other']['env_keys'] == ['KEEP_ME']
        assert parsed['launch']['argv'][-1] == 'agentbench.sdk.plugin.kuma.worker'
    assert manifest.read_text() == source


def test_merge_is_idempotent_and_preserves_environment_string_values():
    source = '[runtime]\nenv_keys = ["value]#not-a-comment", "KUMA_API_KEY"]\n'
    once = extend_runtime_environment(source, ('KUMA_API_KEY', 'DEFUZEX_API_KEY'))
    assert extend_runtime_environment(once, ('KUMA_API_KEY', 'DEFUZEX_API_KEY')) == once
    assert tomllib.loads(once)['runtime']['env_keys'][0] == 'value]#not-a-comment'


@pytest.mark.parametrize('value', ['"DATABASE_HOST"', '[12]', '[""]'])
def test_invalid_environment_list_is_rejected(value):
    with pytest.raises(ValueError, match='runtime.env_keys'):
        extend_runtime_environment('[runtime]\nenv_keys = ' + value, ('KUMA_API_KEY',))
