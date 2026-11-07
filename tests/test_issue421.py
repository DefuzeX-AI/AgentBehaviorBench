"""Issue #421: Case networks are reused within a Suite instead of churned per Case."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from agentbench.runtime.contracts.execution import DockerCleanupError, RunControl
from agentbench.runtime.docker.network_pool import NetworkPool
from agentbench.runtime.docker.runtime import DockerRuntimeError
from agentbench.runtime.services import RuntimeServices


@pytest.fixture
def suite(tmp_path, monkeypatch):
    import agentbench.runtime.docker.runtime as module
    services = RuntimeServices(environ={})
    config = SimpleNamespace(build_context=tmp_path, dockerfile=tmp_path / "Dockerfile",
                             agent_id="test-agent", environment={}, workdir="/app",
                             argv=["echo", "test"], timeout_sec=3,
                             model_target=None, model_metadata_paths=(), replacement_model_provider=None)
    monkeypatch.setattr(module.AgentContainerConfig, "from_agent_dir", lambda *args, **kwargs: config)
    monkeypatch.setattr(module.InterceptionConfig, "from_agent_dir", lambda *args, **kwargs: None)
    calls: list[list[str]] = []
    state = {"attached": "0", "container_rm_fails": False}

    def command(args, **kwargs):
        args = list(args)
        calls.append(args)
        if args[0] == "create":
            # Stop each Case right after its network is leased.
            return subprocess.CompletedProcess(args, 1, "", "agent create refused")
        if args[:2] == ["network", "inspect"]:
            return subprocess.CompletedProcess(args, 0, state["attached"] + "\n", "")
        if state["container_rm_fails"] and args[:2] == ["container", "rm"]:
            return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")
        return subprocess.CompletedProcess(args, 0, "id", "")

    def run_case():
        runtime = services.create_docker_runtime(control=RunControl(), run_id="artifact-1",
                                                 identity={"suite_id": "suite-1", "job_id": "job-1"})
        runtime._images = SimpleNamespace(build=lambda **kwargs: "image:cached")
        runtime._commands = SimpleNamespace(run=command)
        runtime.start(SimpleNamespace(path=tmp_path))

    return SimpleNamespace(services=services, calls=calls, state=state, run_case=run_case)


def _creates(calls):
    return [args for args in calls if args[:2] == ["network", "create"]]


def _removes(calls):
    return [args for args in calls if args[:2] == ["network", "rm"]]


def test_sequential_cases_reuse_one_network_until_suite_close(suite):
    for _ in range(3):
        with pytest.raises(DockerRuntimeError, match="agent create refused"):
            suite.run_case()
    creates = _creates(suite.calls)
    assert len(creates) == 1
    assert "--internal" in creates[0] and "defuzex.pool=1" in creates[0]
    assert not _removes(suite.calls)
    agent_networks = {args[args.index("--network") + 1] for args in suite.calls if args[0] == "create"}
    assert agent_networks == {creates[0][-1]}

    suite.services.close()
    assert [args[-1] for args in _removes(suite.calls)] == [creates[0][-1]]
    assert all(item["status"] == "removed" for item in suite.services.resource_registry.snapshot())


def test_network_with_leftover_container_is_retired_not_shared(suite):
    with pytest.raises(DockerRuntimeError):
        suite.run_case()
    suite.state["attached"] = "1"
    with pytest.raises(DockerRuntimeError):
        suite.run_case()
    first, second = (args[-1] for args in _creates(suite.calls))
    assert first != second
    assert [args[-1] for args in _removes(suite.calls)] == [first]


def test_failed_container_cleanup_removes_network_instead_of_reusing_it(suite):
    suite.state["container_rm_fails"] = True
    with pytest.raises(DockerCleanupError):
        suite.run_case()
    created = _creates(suite.calls)[0][-1]
    assert [args[-1] for args in _removes(suite.calls)] == [created]
    suite.state["container_rm_fails"] = False
    with pytest.raises(DockerRuntimeError):
        suite.run_case()
    assert len(_creates(suite.calls)) == 2


def test_pool_leases_are_exclusive_and_kind_specific():
    pool = NetworkPool()
    removed = []
    egress, internal = pool.new_name(False), pool.new_name(True)
    for name in (egress, internal):
        pool.adopt(name, removed.append)
    assert egress.endswith("-egress") and internal.endswith("-internal")
    assert pool.take(False) is None
    pool.release(egress, False)
    pool.release(internal, True)
    assert pool.take(True) == internal
    assert pool.take(True) is None
    assert pool.take(False) == egress
    assert pool.close() == []
    assert sorted(removed) == sorted([egress, internal])


def test_network_lease_and_daemon_check_have_distinct_timing_stages(suite, tmp_path):
    from agentbench.observe.timing import timing_session
    from agentbench.observe.timeline import timeline
    from agentbench.observe.view_api import RunViewAPI

    try:
        with timing_session(tmp_path / 'timing.jsonl', source='host', name='Case'):
            with pytest.raises(DockerRuntimeError, match='agent create refused'):
                suite.run_case()
        names = [operation['name'] for operation in timeline(RunViewAPI(tmp_path))['operations']]
        assert names.count('Check Docker availability') == 1
        assert names.count('Lease Case network') == 1
    finally:
        suite.services.close()
