"""Whip native configuration and manual-source boundary regressions."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib

import pytest

UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/132-whip'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


launch = module('whip_launcher', UNIT / 'bootstrap/launch.py')
prepare = module('whip_source', UNIT / 'prepare_source.py')


def environment():
    return {'ABB_AGENT_MODEL_API_KEY': 'test-secret', 'ABB_AGENT_MODEL': 'a-model',
            'ABB_AGENT_MODEL_BASE_URL': 'https://models.example.test/v1',
            'HTTPS_PROXY': 'http://interceptor:8080', 'SSL_CERT_FILE': '/cert/ca.pem',
            'OPENAI_API_KEY': 'foreign-secret', 'WHIPCODE_HOME': '/foreign'}


def test_native_config_uses_selected_model_and_keeps_credentials_out_of_files(tmp_path):
    child = launch.prepare(environment(), tmp_path)
    config = Path(child['WHIPCODE_HOME']) / 'config.json'
    data = json.loads(config.read_text())
    assert data['models']['abb']['id'] == 'a-model'
    assert data['models']['abb']['context'] >= 8192
    assert data['models']['abb']['maxOut'] >= 1024
    assert data['providers']['abb']['baseUrl'] == 'https://models.example.test/v1'
    assert data['providers']['abb']['apiKeyEnv'] == 'ABB_AGENT_MODEL_API_KEY'
    assert 'test-secret' not in config.read_text()
    assert 'OPENAI_API_KEY' not in child
    assert child['HTTPS_PROXY'] == 'http://interceptor:8080'
    assert child['SSL_CERT_FILE'] == '/cert/ca.pem'
    assert Path(child['WHIPCODE_HOME']).is_relative_to(tmp_path)
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('field', ['ABB_AGENT_MODEL_API_KEY', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL'])
def test_missing_runtime_selection_fails_without_fallback(tmp_path, field):
    env = environment(); env.pop(field)
    with pytest.raises(ValueError, match='required'):
        launch.prepare(env, tmp_path)


@pytest.mark.parametrize('base', ['http://models.test/v1', 'https://key@models.test/v1', 'https://models.test/v1?key=x'])
def test_unsafe_endpoint_rejected_before_writing_config(tmp_path, base):
    env = environment(); env['ABB_AGENT_MODEL_BASE_URL'] = base
    with pytest.raises(ValueError, match='HTTPS'):
        launch.prepare(env, tmp_path)
    assert not list(tmp_path.iterdir())


def test_official_profile_and_shared_adapter_contract():
    from kuma.repository.agent_profiles import parse_agent_profile
    from agentbench.adapter.acp.config import ACPConfig
    data = tomllib.loads((UNIT / 'agent.toml').read_text())
    assert data['source']['method'] == 'bundled'
    assert 'provider' not in data['model']
    assert ACPConfig.from_agent_dir(UNIT).cwd == data['evaluation']['workspace']['path']
    assert parse_agent_profile(UNIT / 'requirement.md').input_type == 'text'


def source_fixture(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    monkeypatch.setattr(subprocess, 'check_output', lambda args, **kwargs: str(source) if args[-1] == '--show-toplevel' else prepare.REVISION if args[-1] == 'HEAD' else '')
    return source


def test_materializes_internal_directory_without_changing_source(tmp_path, monkeypatch):
    source = source_fixture(tmp_path, monkeypatch)
    (source / 'skills').mkdir(); (source / 'skills/tool.txt').write_text('original\n')
    (source / 'linked').symlink_to('skills', target_is_directory=True)
    destination = tmp_path / 'agent'
    prepare.materialize(source, destination)
    assert (source / 'linked').is_symlink()
    assert not (destination / 'linked').is_symlink()
    assert (destination / 'linked/tool.txt').read_bytes() == b'original\n'
    with pytest.raises(ValueError, match='already exists'):
        prepare.materialize(source, destination)


def test_rejects_escape_before_copying(tmp_path, monkeypatch):
    source = source_fixture(tmp_path, monkeypatch)
    (source / 'escape').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='unsafe'):
        prepare.materialize(source, tmp_path / 'agent')
    assert not (tmp_path / 'agent').exists()


def test_rejects_checkout_subdirectory(tmp_path, monkeypatch):
    source = source_fixture(tmp_path, monkeypatch)
    nested = source / 'nested'; nested.mkdir()
    with pytest.raises(ValueError, match='complete Git checkout root'):
        prepare.materialize(nested, tmp_path / 'agent')
    assert not (tmp_path / 'agent').exists()


def test_rejects_ignored_artifacts_before_copy(tmp_path, monkeypatch):
    source = source_fixture(tmp_path, monkeypatch)
    calls = []
    def git(args, **kwargs):
        calls.append(args)
        if args[-1] == '--show-toplevel': return str(source)
        if args[-1] == 'HEAD': return prepare.REVISION
        return '!! ignored-private-file\n' if '--ignored' in args else ''
    monkeypatch.setattr(subprocess, 'check_output', git)
    with pytest.raises(ValueError, match='ignored files'):
        prepare.materialize(source, tmp_path / 'agent')
    assert any('--ignored' in call for call in calls)
    assert not (tmp_path / 'agent').exists()
