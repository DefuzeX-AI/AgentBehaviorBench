"""Runtime facts are independent of any SDK's document or wire format."""
import json
from types import SimpleNamespace

from agentbench.runtime.agentcontainer.environment import observe_environment
from agentbench.runtime.contracts.environment import ExecutionEnvironment
from agentbench.runtime.docker.environment import describe_environment
from agentbench.runtime.docker.policy import DockerPolicy, EgressSettings


def test_description_uses_effective_flags_and_never_includes_host_paths_or_secrets():
    arguments = [*DockerPolicy(cpus=2, memory='2g', pids_limit=64).run_arguments(),
                 '--mount', 'type=bind,source=/private/secret-project,target=/workspace/task',
                 '--mount', 'type=bind,source=/private/input,target=/run/abb-input,readonly',
                 '--env', 'API_KEY=not-for-upload']
    environment = describe_environment(arguments, workdir='/opt/agent', timeout=123,
                                      egress=EgressSettings(), interception=SimpleNamespace())
    value = environment.as_dict()
    assert value['limits'] == {'cpus': '2', 'memory': '2g', 'pids-limit': '64', 'timeout_seconds': 123}
    assert value['filesystem']['mounts'][-1] == {'path': '/run/abb-input', 'kind': 'bind', 'read_only': True}
    assert value['filesystem']['mounts'][-2]['read_only'] is False
    assert value['network']['other_egress'] == 'observe'
    assert value['network']['loopback'] == 'native_unobserved'
    assert value['network']['external_non_dns_udp'] == 'blocked'
    assert value['filesystem']['root_read_only'] is False
    assert '/private' not in json.dumps(value) and 'API_KEY' not in json.dumps(value)
    assert ExecutionEnvironment.from_dict(json.loads(json.dumps(value))) == environment


def test_unintercepted_network_is_internal_even_with_open_egress_setting():
    environment = describe_environment(['--read-only'], workdir='/app', timeout=60,
                                      egress=EgressSettings(mode='open'), interception=None)
    assert environment.network == {'mode': 'internal'}
    assert environment.filesystem['root_read_only'] is True
    assert environment.limits == {'timeout_seconds': 60}


def test_process_observation_does_not_invent_tools_or_dump_environment(monkeypatch):
    monkeypatch.setenv('SECRET_API_KEY', 'do-not-export')
    monkeypatch.setattr('shutil.which', lambda name: '/bin/python' if name == 'python' else None)
    observed = observe_environment()
    assert observed.runtime == 'unknown'
    assert observed.limits == {} and observed.workspace is None
    assert observed.process['programs_on_path'] == ['python']
    assert 'do-not-export' not in json.dumps(observed.as_dict())
