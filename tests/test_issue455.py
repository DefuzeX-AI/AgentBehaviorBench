"""Verify the AutoDev published-package ACP integration contract."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'resources/agents/131-autodev'


def launcher():
    spec = importlib.util.spec_from_file_location('autodev_launcher', UNIT / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection():
    return {'ABB_AGENT_MODEL_API_KEY':'synthetic-only-test-key',
            'ABB_AGENT_MODEL_BASE_URL':'https://fixture.example/api/v3',
            'ABB_AGENT_MODEL':'selected-test-model', 'SSL_CERT_FILE':'/runtime/ca.pem'}


def test_runtime_selection_reaches_native_config_without_cli_secret(tmp_path):
    env = selection()
    command, child = launcher().prepare(env, tmp_path)
    config_file = tmp_path / '.autodev/config.yaml'
    config = json.loads(config_file.read_text())
    assert command[-1] == 'acp'
    assert env['ABB_AGENT_MODEL_API_KEY'] not in repr(command)
    assert config['configs'] == [{'name':'abb', 'provider':'custom-openai-base',
        'model':'selected-test-model', 'baseUrl':'https://fixture.example/api/v3/',
        'apiKey':'synthetic-only-test-key'}]
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_file.parent.stat().st_mode) == 0o700
    assert child['NODE_EXTRA_CA_CERTS'] == '/runtime/ca.pem'
    assert child['HOME'] == str(tmp_path)
    assert env == selection()


@pytest.mark.parametrize('missing', ['ABB_AGENT_MODEL_API_KEY', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL'])
def test_incomplete_selection_does_not_write_config(tmp_path, missing):
    env = selection()
    del env[missing]
    with pytest.raises(ValueError, match=missing):
        launcher().prepare(env, tmp_path)
    assert not (tmp_path / '.autodev').exists()


@pytest.mark.parametrize('url', ['http://fixture.example/v1', 'https://user:password@fixture.example/v1',
                               'https://fixture.example/v1?token=secret', 'https://fixture.example/v1#fragment'])
def test_unsafe_endpoints_fail_before_writing_credentials(tmp_path, url):
    env = selection(); env['ABB_AGENT_MODEL_BASE_URL'] = url
    with pytest.raises(ValueError):
        launcher().prepare(env, tmp_path)
    assert not (tmp_path / '.autodev').exists()


def test_clean_install_preparation_and_official_profile_validation(tmp_path):
    from agentbench.runtime.source.preparation import prepare_agent_source
    from agentbench.onboarding.build_agent_env.common.validation import validate_unit
    from agentbench.sdk.plugin.kuma.plugin import plugin
    target = tmp_path / 'autodev'
    shutil.copytree(UNIT, target, ignore=shutil.ignore_patterns('agent', '__pycache__'))
    assert not (target / 'agent').exists()
    prepare_agent_source(target, cache_dir=tmp_path / 'source-cache')
    assert validate_unit(target, plugin, expected_id='autodev') == 'autodev'
    for name in ('package.json','package-lock.json'):
        assert (target / 'agent' / name).read_bytes() == (target / 'install' / name).read_bytes()


def test_published_kotlin_and_cli_artifacts_are_both_locked():
    package = json.loads((UNIT / 'install/package.json').read_text())
    lock = json.loads((UNIT / 'install/package-lock.json').read_text())
    for name in ('@xiuper/cli','@xiuper/mpp-core'):
        assert package['dependencies'][name] == '1.0.2'
        entry = lock['packages']['node_modules/' + name]
        assert entry['version'] == '1.0.2'
        assert entry['resolved'].startswith('https://registry.npmjs.org/')
        assert entry['integrity'].startswith('sha512-')
    assert lock['packages']['']['dependencies'] == package['dependencies']


def test_registry_keeps_uncertified_unit_disabled():
    manifest = tomllib.loads((UNIT / 'agent.toml').read_text())
    registry = tomllib.loads((ROOT / 'resources/registry.toml').read_text())
    record = next(a for a in registry['agents'] if a['agent_id'] == 'autodev')
    assert record['status'] == 'adapting' and record['enabled'] is False
    assert manifest['source']['method'] == 'install'
    assert manifest['source']['revision'] == '47f9aab58f023dc777fbb5f3c71c539fa0a40a82'
    assert manifest['adapter']['permission_policy'] == 'allow_once'
    assert 'model' not in manifest
