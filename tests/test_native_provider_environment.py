"""Shared provider credentials reach the Agent through ABB-owned variables."""

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.sdk.integration import runner as integration_runner
from agentbench.runtime.docker.runtime import DockerRuntimeError, _container_environment
from agentbench.sdk.plugin.native.plugin import plugin
from agentbench.sdk.plugin.native.runner import NativeRunner


def test_shared_provider_credential_is_mapped_to_agent_variables(tmp_path):
    root = tmp_path / 'unit'
    root.mkdir()
    (root / 'agent.toml').write_text(
        'schema_version = "defuzex-bench.agent.v2"\n'
        'agent_id = "provider-fixture"\nframework = "acp"\n'
        '[runtime]\ntype = "docker"\nenv_keys = []\nsecret_env_keys = []\n'
        '[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
        '[launch]\nargv = ["python", "agent.py"]\n'
        '[llm_interception]\nmode = "observe"\n')
    (root / 'Dockerfile').write_text('FROM python:3.12-slim\nUSER 10001\n')
    provider_catalog = tmp_path / 'providers.toml'
    provider_catalog.write_text(
        'priority = ["stepfun"]\n'
        '[providers.stepfun]\n'
        'credential_env = "STEPFUN_API_KEY"\n'
        'model_env = "STEPFUN_MODEL"\n'
        'base_url_env = "STEPFUN_BASE_URL"\n'
        'base_url = "https://api.stepfun.com/step_plan/v1"\n'
        'target_plugin = "compatible-json"\n'
        '[providers.stepfun.endpoint_paths]\n'
        '"/chat/completions" = "/chat/completions"\n')
    secret = 'synthetic-provider-token-for-forwarding'
    environ = {
        'ABB_MODEL': 'step-5-preview',
        'ABB_MODEL_PROVIDERS_CONFIG': str(provider_catalog),
        'ABB_MODEL_PROVIDER': 'stepfun',
        'STEPFUN_API_KEY': secret,
    }
    runtime = AgentContainerConfig.from_agent_dir(
        root, secret_resolver=EnvironmentSecretResolver(environ), environ=environ)
    assert runtime.environment == {
        'ABB_AGENT_MODEL_API_KEY': secret,
        'ABB_AGENT_MODEL_BASE_URL': 'https://api.stepfun.com/step_plan/v1',
        'ABB_AGENT_MODEL': 'step-5-preview',
        'ABB_AGENT_MODEL_PROVIDER': 'stepfun',
    }
    assert 'STEPFUN_API_KEY' not in runtime.environment
    assert 'worker_env_keys' not in (root / 'agent.toml').read_text()


def test_native_runner_excludes_model_credentials_from_controller(monkeypatch, tmp_path):
    captured = {}

    root = tmp_path / 'unit'
    root.mkdir()
    (root / 'agent.toml').write_text(
        'schema_version = "defuzex-bench.agent.v2"\n'
        'agent_id = "provider-fixture"\nframework = "acp"\n'
        '[runtime]\ntype = "docker"\nworker_env_keys = ["STEPFUN_API_KEY"]\n'
        '[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
        '[launch]\nargv = ["python", "agent.py"]\n'
        '[llm_interception]\nmode = "observe"\n')
    catalog = tmp_path / 'providers.toml'
    catalog.write_text(
        'priority = ["stepfun"]\n'
        '[providers.stepfun]\n'
        'credential_env = "STEPFUN_API_KEY"\n'
        'model_env = "STEPFUN_MODEL"\n'
        'base_url_env = "STEPFUN_BASE_URL"\n'
        'base_url = "https://api.stepfun.com/step_plan/v1"\n'
        'target_plugin = "compatible-json"\n'
        '[providers.stepfun.endpoint_paths]\n'
        '"/chat/completions" = "/chat/completions"\n')

    def run_evaluation(registration, **kwargs):
        captured.update(kwargs)
        return 'run result'

    monkeypatch.setattr(integration_runner, 'run_evaluation', run_evaluation)
    secret = '{{SYNTHETIC_STEPFUN_SECRET}}'
    context = SimpleNamespace(environ={
        'ABB_MODEL': 'environment-default',
        'ABB_MODEL_PROVIDER': 'stepfun',
        'ABB_MODEL_PROVIDERS_CONFIG': str(catalog),
        'STEPFUN_API_KEY': secret,
    }, model='step-5-preview')
    runner = NativeRunner(plugin, context=context, options={})
    result = runner._run(SimpleNamespace(path=root), settings={}, context=context, on_progress=None)

    assert result == 'run result'
    assert captured['excluded_controller_environment'] == (
        'ABB_AGENT_MODEL_API_KEY', 'STEPFUN_API_KEY')
    assert secret not in str(captured['excluded_controller_environment'])


def test_container_environment_keeps_values_out_of_docker_argv():
    secret = '{{SYNTHETIC_PROVIDER_SECRET}}'
    environ = {
        'STEPFUN_API_KEY': secret,
        'ABB_AGENT_MODEL': 'step-5-preview',
        'SDK_PRIVATE_TOKEN': '{{SYNTHETIC_EXCLUDED_SECRET}}',
    }
    options, command_environment = _container_environment(
        environ, excluded=('SDK_PRIVATE_TOKEN',))

    assert options == ('--env', 'ABB_AGENT_MODEL', '--env', 'STEPFUN_API_KEY')
    assert secret not in options
    assert '{{SYNTHETIC_EXCLUDED_SECRET}}' not in command_environment.values()
    assert command_environment == {
        'STEPFUN_API_KEY': secret,
        'ABB_AGENT_MODEL': 'step-5-preview',
    }


def test_container_environment_preserves_multiline_values():
    value = 'first line\nsecond line\r\n'
    options, command_environment = _container_environment({'MCP_TEST_VALUE': value})

    assert options == ('--env', 'MCP_TEST_VALUE')
    assert command_environment == {'MCP_TEST_VALUE': value}


def test_docker_command_receives_values_in_environment_not_arguments(monkeypatch):
    from agentbench.runtime.docker.command import DockerCommandRunner

    secret = 'first line\nsecond line'
    captured = {}

    class Process:
        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    runner = DockerCommandRunner(executable='docker', environ={'PATH': '/usr/bin'})

    def start(arguments, **kwargs):
        captured['arguments'] = arguments
        captured['environment'] = kwargs['env']
        return Process()

    monkeypatch.setattr(runner, 'start', start)
    result = runner.run(['create', '--env', 'MCP_TEST_VALUE', 'fixture'],
                        extra_environ={'MCP_TEST_VALUE': secret}, timeout=1)

    assert result.returncode == 0
    assert secret not in captured['arguments']
    assert captured['environment']['MCP_TEST_VALUE'] == secret


@pytest.mark.parametrize('key,value', [('BAD=KEY', 'value'), ('MCP_TEST_VALUE', 'null\x00byte')])
def test_container_environment_rejects_unrepresentable_entries(key, value):
    with pytest.raises(DockerRuntimeError, match='valid names and NUL-free values'):
        _container_environment({key: value})
