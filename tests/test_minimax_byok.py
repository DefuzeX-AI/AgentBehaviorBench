"""MiniMax's outer BYOK bootstrap uses its native CLI without leaking credentials."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import subprocess
from unittest.mock import Mock

import pytest
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts.secrets import EnvironmentSecretResolver, MissingSecretError

UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/16-minimax-code'


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location('minimax_byok_bootstrap', UNIT / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture_unit(tmp_path):
    root = tmp_path / 'unit'
    (root / 'bootstrap').mkdir(parents=True)
    (root / 'bootstrap/native-config.yaml').write_text('minimax_api:\n  baseURL: https://api.example/anthropic\n')
    return root


def test_real_secret_private_profile_and_clean_stdio(launcher, fixture_unit, tmp_path, monkeypatch):
    seen = []
    def native_setup(command, **options):
        seen.append((command, options))
        config = Path(options['env']['MINIMAX_DATA_DIR']) / 'config.yaml'
        assert config.stat().st_mode & 0o777 == 0o600
        assert 'baseURL: https://api.example/anthropic' in config.read_text()
        assert 'private-test-key' not in repr(command)
        assert options['env']['MINIMAX_API_KEY'] == 'private-test-key'
        assert options['stdout'] == subprocess.PIPE
        return SimpleNamespace(returncode=0, stdout='native setup status')
    monkeypatch.setattr(launcher.subprocess, 'run', native_setup)
    env = {'MINIMAX_API_KEY':'private-test-key', 'MINIMAX_DATA_DIR':str(tmp_path/'profiles')}
    first = launcher.prepare(fixture_unit, env)
    second = launcher.prepare(fixture_unit, env)
    assert first[1]['MINIMAX_DATA_DIR'] != second[1]['MINIMAX_DATA_DIR']
    assert env['MINIMAX_DATA_DIR'] == str(tmp_path/'profiles')
    assert seen[0][0][-4:] == ['provider', 'set-minimax-key', '--api-key-env', 'MINIMAX_API_KEY']
    assert Path(first[1]['MINIMAX_DATA_DIR']).stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('failure', ['exit', 'timeout'])
def test_setup_failure_cleans_up_and_does_not_launch_acp(launcher, fixture_unit, tmp_path, monkeypatch, failure):
    call = Mock(return_value=SimpleNamespace(returncode=1, stdout='error with private-test-key'))
    if failure == 'timeout':
        call.side_effect = subprocess.TimeoutExpired(['node'], 45, output='private-test-key')
    monkeypatch.setattr(launcher.subprocess, 'run', call)
    with pytest.raises(RuntimeError) as caught:
        launcher.prepare(fixture_unit, {'MINIMAX_API_KEY':'private-test-key', 'MINIMAX_DATA_DIR':str(tmp_path/'profiles')})
    assert 'private-test-key' not in str(caught.value)
    assert list((tmp_path/'profiles').iterdir()) == []


def test_missing_key_fails_before_startup(launcher, fixture_unit, monkeypatch):
    native = Mock()
    monkeypatch.setattr(launcher.subprocess, 'run', native)
    with pytest.raises(ValueError, match='MINIMAX_API_KEY is required'):
        launcher.prepare(fixture_unit, {})
    native.assert_not_called()


def test_global_unit_observes_only_declared_native_model_endpoints():
    config = InterceptionConfig.from_agent_dir(UNIT)
    assert config.mode == 'observe'
    assert config.environment['MAVIS_REGION'] == 'en'
    assert [c.agent_env for c in config.credentials] == ['MINIMAX_API_KEY']
    for path in ('/anthropic/v1/messages', '/anthropic/v1/messages/count_tokens'):
        assert any(r.matches(host='api.minimax.io', port=443, method='POST', path=path) for r in config.routes)
    assert not any('api.minimax.cn' in r.host_patterns for r in config.routes)
    assert {h for r in config.tool_routes for h in r.host_patterns} == {
        'models.dev', 'agent.minimax.io', 'agent.minimaxi.com',
    }
    assert any(
        r.host_patterns == ('agent.minimaxi.com',)
        and r.ports == (443,)
        and r.methods == ('POST',)
        and r.path_patterns == ('/mavis/api/v1/content',)
        and r.required is False
        for r in config.tool_routes
    )
    assert not any(r.matches(host='agent.minimax.io', port=443, method='POST',
                             path='/mavis/api/v1/llm/v1/messages') for r in config.routes)


def test_manifest_requires_real_key_before_container_start():
    with pytest.raises(MissingSecretError, match='MINIMAX_API_KEY'):
        AgentContainerConfig.from_agent_dir(UNIT, secret_resolver=EnvironmentSecretResolver({}), environ={})


def test_native_responses_count_route_is_auxiliary_and_narrow():
    config = InterceptionConfig.from_agent_dir(UNIT)
    matches = [r for r in config.routes if r.matches(host='api.minimax.io', port=443,
        method='POST', path='/v1/responses/input_tokens')]
    assert len(matches) == 1
    assert matches[0].protocol_plugin == 'openai-input-tokens'
    assert not matches[0].matches(host='api.minimax.io', port=443, method='POST', path='/v1/responses')
    assert not matches[0].matches(host='api.minimax.io', port=443, method='GET', path='/v1/responses/input_tokens')
    assert config.mode == 'observe' and not config.token_counting
