"""Issue #491: Easy Code runs its native ACP server on the shared model as a custom model."""
import importlib.util
import json
import stat

import pytest
from kuma.repository.agent_profiles import parse_agent_profile

from agentbench.harness.registry import tomllib
from tests.registered_agents import unit

ENV = {'ABB_AGENT_MODEL_API_KEY': 'synthetic-selected-key',
       'ABB_AGENT_MODEL_BASE_URL': 'https://api.deepseek.com/',
       'ABB_AGENT_MODEL': 'deepseek-chat'}


def launcher():
    spec = importlib.util.spec_from_file_location('issue491_easycode', unit('easycode') / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unit_is_registered_as_adapting_install_source():
    with (unit('easycode') / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    assert manifest['source']['method'] == 'install'
    assert len(manifest['source']['revision']) == 40
    assert manifest['runtime']['secret_env_keys'] == []
    assert manifest['adapter']['command'] == ['python', '/opt/agent/bootstrap/launch.py']
    assert manifest['adapter']['permission_policy'] == 'allow_once'
    package = json.loads((unit('easycode') / 'install/package.json').read_text())
    assert package['dependencies'] == {'easycode-ai': '1.1.91'}


def test_key_reaches_only_the_owner_only_custom_model_file(tmp_path):
    module = launcher()
    command, child = module.prepare({**ENV, 'DEEPX_WEB_URL': 'https://elsewhere.example',
                                     'EASYCODE_CUSTOM_MODELS_FILE': '/tmp/other.json'}, tmp_path)
    module.seed_home(tmp_path, module.custom_model(ENV))
    assert command[-1] == '--acp' and command[1].endswith('easycode-ai/bundle/easycode.js')
    assert ENV['ABB_AGENT_MODEL_API_KEY'] not in json.dumps([command, child])
    assert 'DEEPX_WEB_URL' not in child and 'EASYCODE_CUSTOM_MODELS_FILE' not in child
    assert child['HOME'] == str(tmp_path)
    models = tmp_path / '.easycode-user/custom-models.json'
    assert stat.S_IMODE(models.stat().st_mode) == 0o600
    assert json.loads(models.read_text()) == {'models': [{
        'displayName': 'abb', 'provider': 'openai', 'baseUrl': 'https://api.deepseek.com',
        'apiKey': 'synthetic-selected-key', 'modelId': 'deepseek-chat'}]}
    # The session must start on the custom model; "auto" needs Easy Code's server.
    settings = json.loads((tmp_path / '.easycode-user/settings.json').read_text())
    assert settings == {'preferredModel': 'custom:abb'}


def test_existing_model_file_is_not_overwritten(tmp_path):
    module = launcher()
    module.seed_home(tmp_path, module.custom_model(ENV))
    with pytest.raises(FileExistsError):
        module.seed_home(tmp_path, module.custom_model(ENV))


@pytest.mark.parametrize('name,value', [('ABB_AGENT_MODEL_API_KEY', ''), ('ABB_AGENT_MODEL', ''),
                                        ('ABB_AGENT_MODEL_BASE_URL', 'http://api.deepseek.com'),
                                        ('ABB_AGENT_MODEL_BASE_URL', 'https://api.deepseek.com?x=1')])
def test_invalid_selection_is_rejected_before_any_file(tmp_path, name, value):
    module = launcher()
    with pytest.raises(ValueError):
        module.custom_model({**ENV, name: value})
    assert list(tmp_path.iterdir()) == []


def test_profile_parses_within_the_case_generation_budget():
    profile = parse_agent_profile(unit('easycode') / 'requirement.md')
    assert profile.strategy_group.id == 'basic-safety-coding'
    sections = dict(profile.sections)
    assert all(len(sections[key]) < 4000 for key in
               ('production_scenario', 'behaviors_to_test', 'prohibited_behaviors'))
    assert '[TITLE_UPDATE]' in sections['prohibited_behaviors']
