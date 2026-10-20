import math
import os
import subprocess
from uuid import uuid4

import pytest

from agentbench.runtime.docker.policy import (
    CPUS_ENV,
    MEMORY_ENV,
    DockerPolicy,
    EgressSettings,
    _validate_docker_cpus,
    _validate_docker_memory,
)
from agentbench.runtime.docker.runtime import DockerRuntime


def test_agent_can_write_home_and_execute_large_temporary_workspace():
    image = os.environ.get("ABB_DOCKER_CASE_BASE_IMAGE")
    if not image:
        pytest.skip("Set ABB_DOCKER_CASE_BASE_IMAGE to an installed non-root Python image")
    name = "abb-policy-test-" + uuid4().hex
    script = """
import os
import sqlite3
import subprocess
from pathlib import Path
assert os.getuid() != 0, 'Acceptance requires the native non-root image user'
home = Path.home() / 'abb-policy-acceptance'
home.mkdir()
with sqlite3.connect(home / 'state.sqlite') as connection:
    connection.execute('create table state (value text)')
    connection.execute("insert into state values ('persisted')")
    assert connection.execute('select value from state').fetchone() == ('persisted',)
workspace = Path('/tmp/abb-policy-acceptance')
workspace.mkdir()
with (workspace / 'cache.bin').open('wb') as stream:
    for _ in range(65):
        stream.write(b'x' * (1024 * 1024))
program = workspace / 'check.sh'
program.write_text('#!/bin/sh\\nprintf executable')
program.chmod(0o700)
assert subprocess.check_output([str(program)], text=True) == 'executable'
print('Native user: HOME read/write, SQLite, 65 MiB cache, /tmp execution passed')
"""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--pull=never", "--network=none", "--name", name,
             *DockerPolicy().run_arguments(), "--entrypoint", "python", image, "-c", script],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


def test_docker_policy_defaults_ignore_ambient_environ(monkeypatch):
    """Verify DockerPolicy() constructor defaults ignore ambient process environment variables."""
    monkeypatch.setenv(MEMORY_ENV, "16g")
    monkeypatch.setenv(CPUS_ENV, "8")

    policy = DockerPolicy()
    assert policy.memory == "1g"
    assert policy.cpus == 1.0
    args = policy.run_arguments()
    assert "--memory=1g" in args
    assert "--cpus=1.0" in args or "--cpus=1" in args


def test_docker_policy_explicit_arguments_preserved(monkeypatch):
    """Verify explicit constructor arguments are never overwritten by ambient variables."""
    monkeypatch.setenv(MEMORY_ENV, "16g")
    monkeypatch.setenv(CPUS_ENV, "8")

    policy_default_values = DockerPolicy(memory="1g", cpus=1.0)
    assert policy_default_values.memory == "1g"
    assert policy_default_values.cpus == 1.0

    policy_custom = DockerPolicy(memory="2g", cpus=2.5)
    assert policy_custom.memory == "2g"
    assert policy_custom.cpus == 2.5
    args = policy_custom.run_arguments()
    assert "--memory=2g" in args
    assert "--cpus=2.5" in args


def test_docker_policy_from_environment_explicit_mapping():
    """Verify DockerPolicy.from_environment resolves configuration from explicit environment mapping."""
    policy = DockerPolicy.from_environment({"ABB_DOCKER_MEMORY": "8g", "ABB_DOCKER_CPUS": "4"})
    assert policy.memory == "8g"
    assert policy.cpus == 4.0
    args = policy.run_arguments()
    assert "--memory=8g" in args
    assert "--cpus=4.0" in args

    # Preserves unconfigured settings from base policy
    base = DockerPolicy(memory="2g", cpus=2.0, pids_limit=256, tmpfs_size="2g")
    policy_base = DockerPolicy.from_environment({"ABB_DOCKER_MEMORY": "4g"}, base=base)
    assert policy_base.memory == "4g"
    assert policy_base.cpus == 2.0
    assert policy_base.pids_limit == 256
    assert policy_base.tmpfs_size == "2g"


def test_docker_policy_from_environment_empty_mapping_no_ambient_bleed(monkeypatch):
    """Verify DockerPolicy.from_environment({}) defaults to 1g / 1.0 CPU without ambient environment bleed."""
    monkeypatch.setenv(MEMORY_ENV, "16g")
    monkeypatch.setenv(CPUS_ENV, "8")

    policy = DockerPolicy.from_environment({})
    assert policy.memory == "1g"
    assert policy.cpus == 1.0
    args = policy.run_arguments()
    assert "--memory=1g" in args
    assert "--cpus=1.0" in args or "--cpus=1" in args


def test_docker_policy_from_environment_none_uses_os_environ(monkeypatch):
    """Verify DockerPolicy.from_environment(None) reads ambient os.environ."""
    monkeypatch.setenv(MEMORY_ENV, "4g")
    monkeypatch.setenv(CPUS_ENV, "2")

    policy_none = DockerPolicy.from_environment(None)
    assert policy_none.memory == "4g"
    assert policy_none.cpus == 2.0

    policy_no_arg = DockerPolicy.from_environment()
    assert policy_no_arg.memory == "4g"
    assert policy_no_arg.cpus == 2.0


def test_docker_policy_strict_validation():
    """Verify strict validation of memory and cpus in constructor and factory."""
    # 1. Valid memory values
    for mem in ["512m", "1g", "8g", "16G", "4096M", "1024k", "2K"]:
        assert _validate_docker_memory(mem) == mem.strip()
        p = DockerPolicy(memory=mem)
        assert p.memory == mem.strip()
        p_env = DockerPolicy.from_environment({MEMORY_ENV: mem})
        assert p_env.memory == mem.strip()

    # 2. Invalid memory values
    for bad_mem in ["", "   ", "0g", "-8g", "8gb", "8", "8.5g", "abc", "none", "8x", "1000", None, 1024]:
        with pytest.raises(ValueError):
            _validate_docker_memory(bad_mem)
        with pytest.raises(ValueError):
            DockerPolicy(memory=bad_mem)
        if isinstance(bad_mem, str):
            with pytest.raises(ValueError):
                DockerPolicy.from_environment({MEMORY_ENV: bad_mem})

    # 3. Valid cpus values
    for c in [0.5, 1.0, 2, 4.0, 8.0, 16.5, 1024.0, "2.5"]:
        val = _validate_docker_cpus(c)
        assert float(val) == float(c)
        p = DockerPolicy(cpus=c)
        assert float(p.cpus) == float(c)
        p_env = DockerPolicy.from_environment({CPUS_ENV: str(c)})
        assert float(p_env.cpus) == float(c)

    # 4. Invalid cpus values
    for bad_c in [0, 0.0, -1, -0.5, 1024.1, 2048.0, float("nan"), float("inf"), float("-inf"), "bad", True, False, None]:
        with pytest.raises(ValueError):
            _validate_docker_cpus(bad_c)
        with pytest.raises(ValueError):
            DockerPolicy(cpus=bad_c)
        if bad_c is not None and not isinstance(bad_c, bool):
            with pytest.raises(ValueError):
                DockerPolicy.from_environment({CPUS_ENV: str(bad_c)})


def test_docker_runtime_resource_resolution(monkeypatch):
    """Verify DockerRuntime resolves resource settings from selected environment mapping."""
    monkeypatch.setenv(MEMORY_ENV, "16g")
    monkeypatch.setenv(CPUS_ENV, "8")

    # Explicit environ mapping
    rt_custom = DockerRuntime(environ={"ABB_DOCKER_MEMORY": "8g", "ABB_DOCKER_CPUS": "4"})
    assert rt_custom.policy.memory == "8g"
    assert rt_custom.policy.cpus == 4.0

    # Empty environ mapping isolates against ambient os.environ
    rt_empty = DockerRuntime(environ={})
    assert rt_empty.policy.memory == "1g"
    assert rt_empty.policy.cpus == 1.0

    # Explicit policy parameter takes precedence over environ
    explicit_policy = DockerPolicy(memory="2g", cpus=2.0)
    rt_override = DockerRuntime(
        environ={"ABB_DOCKER_MEMORY": "8g", "ABB_DOCKER_CPUS": "4"},
        policy=explicit_policy,
    )
    assert rt_override.policy.memory == "2g"
    assert rt_override.policy.cpus == 2.0

    # Default environ (None) reads from ambient os.environ
    rt_ambient = DockerRuntime()
    assert rt_ambient.policy.memory == "16g"
    assert rt_ambient.policy.cpus == 8.0


def test_execution_policies_resource_resolution(tmp_path, monkeypatch):
    """Verify AgentExecutionPolicy and ControllerExecutionPolicy resolve resources via policy/runtime."""
    from agentbench.runtime.docker.execution_policy import AgentExecutionPolicy, ControllerExecutionPolicy
    from agentbench.sdk.integration.context import ExecutionChannel

    monkeypatch.setenv(MEMORY_ENV, "16g")
    monkeypatch.setenv(CPUS_ENV, "8")

    channel = ExecutionChannel.create(tmp_path / "channel")
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    storage = tmp_path / "storage"
    storage.mkdir()

    # 1. Default constructor defaults to 1g / 1.0 CPU without ambient bleed
    agent_default = AgentExecutionPolicy(repo, "/workspace", True, channel, out)
    assert "--memory=1g" in agent_default.run_arguments()
    assert "--cpus=1.0" in agent_default.run_arguments() or "--cpus=1" in agent_default.run_arguments()

    ctrl_default = ControllerExecutionPolicy(storage, repository=repo, channel=channel)
    assert "--memory=1g" in ctrl_default.run_arguments()
    assert "--cpus=1.0" in ctrl_default.run_arguments() or "--cpus=1" in ctrl_default.run_arguments()

    # 2. Explicit base policy constructor preserves limits
    custom_policy = DockerPolicy(memory="4g", cpus=2.0)
    agent_custom = AgentExecutionPolicy(repo, "/workspace", True, channel, out, policy=custom_policy)
    assert "--memory=4g" in agent_custom.run_arguments()
    assert "--cpus=2.0" in agent_custom.run_arguments()

    # 3. DockerRuntime initializes execution policy from runtime selected environment
    agent_for_rt = AgentExecutionPolicy(repo, "/workspace", True, channel, out)
    rt = DockerRuntime(
        environ={"ABB_DOCKER_MEMORY": "8g", "ABB_DOCKER_CPUS": "4"},
        policy=agent_for_rt,
    )
    args = rt.policy.run_arguments()
    assert "--memory=8g" in args
    assert "--cpus=4.0" in args

    # 4. DockerRuntime isolates empty environ against ambient bleed
    agent_for_empty_rt = AgentExecutionPolicy(repo, "/workspace", True, channel, out)
    rt_empty = DockerRuntime(environ={}, policy=agent_for_empty_rt)
    args_empty = rt_empty.policy.run_arguments()
    assert "--memory=1g" in args_empty
    assert "--cpus=1.0" in args_empty or "--cpus=1" in args_empty
