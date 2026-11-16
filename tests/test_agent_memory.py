"""Per-Agent memory must not change controller isolation or other resource limits."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from agentbench.runtime.agentcontainer.config import (
    AgentContainerConfig, ContainerConfigurationError,
)
from agentbench.runtime.docker.execution_policy import AgentExecutionPolicy, ControllerExecutionPolicy
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.sdk.integration.context import ExecutionChannel
from agentbench.sdk.integration.execution import run_evaluation
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.onboarding.build_agent_env.build_toml.options import ManifestOptions
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.test_agent_manifest_generation import facts, render
from tests.agent_build_fixtures import source
from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage
from tests.test_docker_concurrency import fake_agent_runtime


@pytest.fixture
def unit(tmp_path):
    (tmp_path / 'Dockerfile').write_text('FROM scratch\n')
    (tmp_path / 'agent.toml').write_text('''agent_id="memory-test"
[runtime]
type="docker"
[build]
context="."
dockerfile="Dockerfile"
[launch]
argv=["python","worker.py"]
''')
    return tmp_path


@pytest.mark.parametrize('value', [True, 2, 2.5, [], {}, '', ' ', '2g ', ' 2g', '0', '0g',
                                    '-1g', '1.5g', '1m', '5m', '2gb', '1e9', 'inf',
                                    '2g --privileged', '2g\n', '9' * 5000, '9223372036854775808'])
def test_invalid_manifest_memory_fails_before_secrets_or_model_selection(unit, value):
    class NoSecrets:
        def require(self, name):
            raise AssertionError('Invalid memory must fail before secret/model work')
    # JSON values are valid TOML for these scalar/list types; mappings need inline TOML.
    encoded = '{bad="value"}' if isinstance(value, dict) else json.dumps(value)
    path = unit / 'agent.toml'
    path.write_text(path.read_text().replace('[runtime]', '[runtime]\nmemory=' + encoded))
    with pytest.raises(ContainerConfigurationError, match='runtime.memory'):
        AgentContainerConfig.from_agent_dir(unit, environ={}, secret_resolver=NoSecrets())


@pytest.mark.parametrize('value,expected', [('2g', '2g'), ('2G', '2g'), ('2048m', '2048m'),
                                           ('2147483648', '2147483648'), ('6291456b', '6291456b')])
def test_valid_memory_is_parsed_and_omission_preserves_default_policy(unit, value, expected):
    assert AgentContainerConfig.from_agent_dir(unit, environ={}, secret_resolver=None,
                                              resolve_model=False).memory is None
    path = unit / 'agent.toml'
    path.write_text(path.read_text().replace('[runtime]', '[runtime]\nmemory=' + json.dumps(value)))
    config = AgentContainerConfig.from_agent_dir(unit, environ={}, secret_resolver=None, resolve_model=False)
    assert config.memory == expected
    assert DockerPolicy().memory == '1g'


def test_sdk_agent_memory_leaves_controller_and_security_arguments_unchanged(tmp_path):
    channel = ExecutionChannel.create(tmp_path / 'channel')
    default = AgentExecutionPolicy(tmp_path, '/workspace', True, channel, tmp_path / 'output')
    selected = AgentExecutionPolicy(tmp_path, '/workspace', True, channel, tmp_path / 'output', memory='2g')
    assert selected.run_arguments() == tuple('--memory=2g' if x == '--memory=1g' else x
                                             for x in default.run_arguments())
    controller = ControllerExecutionPolicy(tmp_path / 'private', repository=tmp_path, channel=channel)
    assert '--memory=1g' in controller.run_arguments()
    assert '--memory=2g' not in controller.run_arguments()
    assert '/run/abb-sdk-storage' not in str(selected.run_arguments())


def test_shared_sdk_execution_applies_memory_only_to_agent(tmp_path):
    agent = source_agent(tmp_path)
    path = agent.path / 'agent.toml'
    path.write_text(path.read_text() + '[runtime]\nmemory="2g"\n')
    services, calls = fake_services()
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None,
                               trace_max_bytes=1024, runtime_services=services)
    run_evaluation(agent, context=context, output=tmp_path / 'runs', stage_agent=unchanged_stage)
    policies = {x['role']: x['options']['policy'].run_arguments() for x in calls}
    assert '--memory=2g' in policies['agent']
    assert '--memory=1g' in policies['controller']


def test_invalid_sdk_memory_creates_no_runtime_or_model_call(tmp_path):
    agent = source_agent(tmp_path)
    path = agent.path / 'agent.toml'
    path.write_text(path.read_text() + '[runtime]\nmemory="unlimited"\n')
    services, calls = fake_services()
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None,
                               trace_max_bytes=1024, runtime_services=services)
    with pytest.raises(ContainerConfigurationError, match='runtime.memory'):
        run_evaluation(agent, context=context, output=tmp_path / 'runs', stage_agent=unchanged_stage)
    assert calls == []


def test_direct_runtime_does_not_leak_memory_into_next_agent(fake_agent_runtime):
    import agentbench.runtime.docker.runtime as module
    runtime, _, services, agent = fake_agent_runtime
    config = module.AgentContainerConfig.from_agent_dir(agent.path)
    seen = []
    def command(args, **kwargs):
        if args[0] == 'create':
            seen.append(list(args))
            raise RuntimeError('Stop before container creation')
        return subprocess.CompletedProcess(args, 0, 'id', '')
    runtime._commands = SimpleNamespace(run=command)
    try:
        for memory in ('2g', None):
            config.memory = memory
            with pytest.raises(RuntimeError, match='Stop before'):
                runtime.start(agent)
        assert '--memory=2g' in seen[0] and '--memory=1g' in seen[1]
        assert runtime._policy.memory == '1g'
        assert [x for x in seen[0] if x.startswith(('--cpus=', '--pids-limit=', '--tmpfs='))] == [
            x for x in seen[1] if x.startswith(('--cpus=', '--pids-limit=', '--tmpfs='))]
    finally:
        services.close()


def test_memory_rendering_is_explicit_operator_policy(source, facts):
    default = render(source, facts)
    assert 'memory' not in default['runtime']
    selected = render(source, facts, options=ManifestOptions(memory='2G'))
    assert selected['runtime']['memory'] == '2g'
    facts['runtime'] = {'memory': '2g'}
    with pytest.raises(BuildError, match='Invalid manifest facts'):
        render(source, facts)
    with pytest.raises(BuildError, match='runtime.memory'):
        ManifestOptions(memory='unlimited')
