"""Reject BBA-owned history before spending on Case generation or execution."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.common.input_binding import validate_input_contract
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner


@pytest.mark.parametrize('contract', [
    {'encoding': 'identity', 'conversation': {'mode': mode}}
    for mode in ('messages', 'text', 'native', 'none')
] + [{}, [], None, {'encoding': 'template'}])
def test_obsolete_or_invalid_contract_fails_during_host_preflight(tmp_path, contract):
    evaluation = tmp_path/'evaluation'
    evaluation.mkdir()
    (tmp_path/'requirement.md').write_text('Not read by input preflight')
    (evaluation/'input-contract.json').write_text(json.dumps(contract))
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'preflight-placeholder'})
    with pytest.raises(ProviderSelectionError, match='native session/context'):
        runner.validate_sdk(SimpleNamespace(path=tmp_path))


def test_all_registered_agents_use_current_input_contract():
    root = Path(__file__).resolve().parents[1]/'resources/agents'
    contracts = list(root.glob('*/evaluation/input-contract.json'))
    assert contracts
    for contract in contracts:
        assert validate_input_contract(contract) is None


def test_contract_validation_does_not_hide_invalid_json(tmp_path):
    path = tmp_path/'input-contract.json'
    path.write_text('{')
    with pytest.raises(ValueError):
        validate_input_contract(path)
