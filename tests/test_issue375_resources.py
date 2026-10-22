"""Optional declared CPU quota preserves all unrelated Docker policy flags."""
from pathlib import Path
import pytest
from agentbench.runtime.agentcontainer.config import AgentContainerConfig, ContainerConfigurationError
from agentbench.onboarding.build_agent_env.build_toml.validation import _PlaceholderSecrets
from agentbench.runtime.docker.policy import DockerPolicy, resource_arguments, EgressSettings
from agentbench.runtime.docker.environment import describe_environment


def config(tmp_path, cpus):
    (tmp_path/'Dockerfile').write_text('FROM python:3.11-slim\n')
    extra='' if cpus is None else '\ncpus='+cpus
    (tmp_path/'agent.toml').write_text('agent_id="cpu-fixture"\nframework="langgraph"\n[runtime]\ntype="docker"'+extra+'\n[build]\ncontext="."\ndockerfile="Dockerfile"\n[launch]\nargv=["python","-V"]\n')
    return AgentContainerConfig.from_agent_dir(tmp_path,secret_resolver=_PlaceholderSecrets(),environ={},resolve_model=False)


@pytest.mark.parametrize('value',[None,'0.5','2','4'])
def test_manifest_cpu_optional_or_valid(tmp_path,value):
    actual=config(tmp_path,value)
    assert actual.cpus==(None if value is None else float(value))


@pytest.mark.parametrize('value',['0','-1','4.1','true','"2"','nan','inf'])
def test_manifest_cpu_invalid_is_rejected(tmp_path,value):
    with pytest.raises(ContainerConfigurationError,match='runtime.cpus'):
        config(tmp_path,value)


def test_cpu_override_preserves_policy_and_observed_environment():
    original=DockerPolicy().run_arguments()
    assert resource_arguments(original)==original
    effective=resource_arguments(original,cpus=2)
    assert set(effective)-set(original)=={'--cpus=2.0'}
    assert set(original)-set(effective)=={'--cpus=1.0'}
    observed=describe_environment(effective,workdir='/opt/agent',egress=EgressSettings(),interception=None,timeout=1800)
    assert observed.limits['cpus']=='2.0'
    assert observed.filesystem['capabilities_dropped']=='ALL'
    assert observed.filesystem['no_new_privileges']
