"""Issue #43 and SDK options: explicit credentials/defaults cross one boundary."""
import inspect

import pytest

from agentbench.sdk.plugin.kuma.configuration import api_key, request_options
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.harness.errors import ProviderSelectionError


def test_key_precedence_and_alias():
    assert api_key({'KUMA_API_KEY': 'first', 'DEFUZEX_API_KEY': 'second'}) == ('first', 'KUMA_API_KEY')
    assert api_key({'KUMA_API_KEY': '', 'DEFUZEX_API_KEY': 'second'}) == ('second', 'DEFUZEX_API_KEY')
    with pytest.raises(ValueError, match='required'):
        api_key({})


def test_omitted_options_use_public_sdk_defaults():
    from kuma import create_run
    options = request_options()
    bound = inspect.signature(create_run).bind_partial(**options)
    bound.apply_defaults()
    assert bound.arguments['max_retries'] == 2
    assert bound.arguments['timeout'] == 300
    assert bound.arguments['operation_wait_timeout'] == 600
    runner = KumaContainerRunner(options={'timeout': 2400, 'sdk_request_options': {'timeout': 30, 'max_retries': 1}})
    assert runner.timeout == 2400
    assert runner.sdk_request_options == {'timeout': 30, 'max_retries': 1}


@pytest.mark.parametrize('value', [{'timeout': 0}, {'timeout': float('inf')}, {'timeout': True},
    {'max_retries': -1}, {'max_retries': 6}, {'api_key': 'forbidden'}, []])
def test_bad_request_options_fail_before_sdk_io(value):
    with pytest.raises(ProviderSelectionError):
        KumaContainerRunner(options={'sdk_request_options': value})
