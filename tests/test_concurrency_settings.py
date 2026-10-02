from types import MappingProxyType

import pytest

from agentbench.harness.concurrency import ConcurrencyConfigurationError, ConcurrencySettings
from agentbench.cli.environment import execution_environment_snapshot, load_execution_environment


def test_default_execution_and_independent_judge_settings():
    assert ConcurrencySettings.from_environ({}).max_parallel_cases == 1
    assert ConcurrencySettings.from_environ({'ABB_MAX_PARALLEL_CASES': ' 4 '}).effective_workers(100) == 4
    assert ConcurrencySettings(4).effective_workers(1) == 1
    defaults = ConcurrencySettings.from_environ({})
    assert defaults.max_parallel_judges == 2
    assert defaults.judge_queue_capacity == 8


@pytest.mark.parametrize('value', ['', ' ', '0', '-1', '1.5', 'true', '+2', 'four', '１２'])
def test_invalid_environment(value):
    with pytest.raises(ConcurrencyConfigurationError, match='ABB_MAX_PARALLEL_CASES'):
        ConcurrencySettings.from_environ({'ABB_MAX_PARALLEL_CASES': value})


@pytest.mark.parametrize('value', [0, -1, True, False, 2.0, '4'])
def test_invalid_python_value(value):
    with pytest.raises(ConcurrencyConfigurationError):
        ConcurrencySettings(value)


def test_env_precedence_and_snapshot(monkeypatch, tmp_path):
    env = tmp_path / '.env'
    env.write_text('ABB_MAX_PARALLEL_CASES=2\n')
    monkeypatch.setenv('ABB_MAX_PARALLEL_CASES', '4')
    loaded = load_execution_environment(env)
    assert loaded.concurrency == ConcurrencySettings(4)
    assert isinstance(loaded.environ, MappingProxyType)
    monkeypatch.setenv('ABB_MAX_PARALLEL_CASES', '8')
    assert loaded.environ['ABB_MAX_PARALLEL_CASES'] == '4'
    assert loaded.concurrency.max_parallel_cases == 4


def test_cli_invalid_worker_count_fails_before_selection(monkeypatch):
    from agentbench.cli.main import cli
    monkeypatch.setenv('ABB_MAX_PARALLEL_CASES', '0')
    assert cli(['run', '--no-view']) == 2
