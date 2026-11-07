"""Issue #280: unattended ACP units must not offer a tool that waits for a human answer."""
import importlib.util
import json

from tests.registered_agents import unit


def launcher(agent):
    spec = importlib.util.spec_from_file_location('issue280_' + agent.replace('-', '_'),
                                                  unit(agent) / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kilo_code_config_file_denies_question(tmp_path):
    module = launcher('kilo-code')
    module.prepare({module.KEY_ENV: 'synthetic-key', module.BASE_URL_ENV: 'https://models.example/v1',
                    module.MODEL_ENV: 'model'}, tmp_path)
    written = json.loads((tmp_path / '.config/kilo/kilo.json').read_text())
    # Kilo resolves the last matching rule; a "*" deny hides the tool from the model.
    assert written['permission']['question'] == 'deny'


def test_openclaw_gateway_config_denies_ask_user():
    config = launcher('openclaw').gateway_config('https://models.example/v1', 'model', 18799,
                                                 '/home/agent/workspace')
    assert 'ask_user' in config['tools']['deny']
