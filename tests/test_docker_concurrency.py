"""Deterministic build coordination and cancellation with real child processes."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agentbench.runtime.contracts.execution import (
    Deadline, DockerCleanupError, RunCancelled, RunControl, RuntimeInfrastructureError,
)
from agentbench.runtime.docker.build_coordinator import BuildCoordinator
from agentbench.runtime.docker.command import DockerCommandRunner, DockerCommandTimeout
from agentbench.runtime.docker.image_builder import DockerBuildError, DockerImageBuilder, _content_digest
from agentbench.runtime.docker.runtime import DockerRuntime
from agentbench.runtime.docker.session import DockerSession
from agentbench.runtime.interception.trace import InterceptionTraceState
from agentbench.runtime.services import RuntimeServices


@pytest.mark.parametrize("failure", ["missing", "unavailable", "timeout"])
def test_docker_unavailable_is_a_suite_infrastructure_failure(monkeypatch, failure):
    runtime = DockerRuntime(environ={})
    def check(*args, **kwargs):
        if failure == "timeout":
            raise DockerCommandTimeout("daemon stopped responding")
        if failure == "missing":
            return None
        return subprocess.CompletedProcess(["docker", "info"], 1, "", "cannot connect")
    monkeypatch.setattr(runtime, "_run_quiet", check)
    with pytest.raises(RuntimeInfrastructureError, match="Docker daemon"):
        runtime._check_available()


def test_same_image_build_is_shared_by_four_callers():
    coordinator = BuildCoordinator()
    barrier = threading.Barrier(4)
    built = []

    def resolve():
        barrier.wait(timeout=2)
        return coordinator.resolve("same", inspect_cached=lambda: None, build_once=build,
                                   deadline=Deadline.after(3))

    def build():
        built.append("image")
        time.sleep(0.1)
        return "image:sha"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: resolve(), range(4)))
    assert results == ["image:sha"] * 4
    assert built == ["image"]


def test_different_image_builds_are_serial_and_cached_images_do_not_wait():
    coordinator = BuildCoordinator()
    started = threading.Event()
    release = threading.Event()
    active = 0
    peak = 0
    lock = threading.Lock()

    def build(key):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            started.set()
            assert release.wait(2)
            return key
        finally:
            with lock:
                active -= 1

    def resolve(key):
        return coordinator.resolve(key, inspect_cached=lambda: None, build_once=lambda: build(key),
                                   deadline=Deadline.after(3))

    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(resolve, "first")
        assert started.wait(1)
        second = pool.submit(resolve, "second")
        cached = pool.submit(coordinator.resolve, "cached", inspect_cached=lambda: "existing",
                             build_once=lambda: pytest.fail("Cache hit built again"))
        try:
            assert cached.result(timeout=1) == "existing"
        finally:
            release.set()
        assert [first.result(timeout=2), second.result(timeout=2)] == ["first", "second"]
    assert peak == 1


def test_cancelled_waiter_does_not_cancel_image_owner():
    coordinator = BuildCoordinator()
    started, release = threading.Event(), threading.Event()
    waiter_control = RunControl()

    def build():
        started.set()
        assert release.wait(3)
        return "image"

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(coordinator.resolve, "image", inspect_cached=lambda: None, build_once=build)
        assert started.wait(1)
        waiter = pool.submit(coordinator.resolve, "image", inspect_cached=lambda: None,
                             build_once=lambda: pytest.fail("Waiter owns no build"), control=waiter_control)
        waiter_control.cancel()
        try:
            with pytest.raises(RunCancelled):
                waiter.result(timeout=1)
            assert not owner.done()
        finally:
            release.set()
        assert owner.result(timeout=1) == "image"


def test_failed_owner_wakes_waiters_and_unknown_daemon_state_stops_new_builds():
    coordinator = BuildCoordinator()
    started, release = threading.Event(), threading.Event()

    def build():
        started.set()
        assert release.wait(2)
        raise RuntimeInfrastructureError("daemon build state unknown")

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(coordinator.resolve, "image", inspect_cached=lambda: None, build_once=build)
        assert started.wait(1)
        waiter = pool.submit(coordinator.resolve, "image", inspect_cached=lambda: None, build_once=build)
        release.set()
        for result in (owner, waiter):
            with pytest.raises(RuntimeInfrastructureError, match="unknown"):
                result.result(timeout=1)
    with pytest.raises(RuntimeInfrastructureError, match="unknown"):
        coordinator.resolve("new", inspect_cached=lambda: None,
                            build_once=lambda: pytest.fail("Must stop new builds"))


@pytest.mark.parametrize("action", ["cancel", "timeout"])
def test_blocked_docker_client_is_interrupted_and_reaped(action):
    commands = DockerCommandRunner(sys.executable)
    launched = []
    original_start = commands.start

    def start(*args, **kwargs):
        process = original_start(*args, **kwargs)
        launched.append(process)
        return process

    commands.start = start
    control = RunControl()
    timer = threading.Timer(0.15, control.cancel)
    if action == "cancel":
        timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(RunCancelled if action == "cancel" else DockerCommandTimeout):
            commands.run(["-c", "import time; time.sleep(30)"], control=control,
                         timeout=5 if action == "cancel" else 0.15)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3
    assert len(launched) == 1 and launched[0].poll() is not None


def test_cancelled_control_still_allows_finite_cleanup_commands():
    control = RunControl()
    control.cancel()
    result = DockerCommandRunner(sys.executable).run(
        ["-c", "print('removed')"], control=control, cleanup=True, timeout=3)
    assert result.returncode == 0 and result.stdout.strip() == "removed"


def test_large_stdout_and_stderr_use_files_and_bounded_diagnostics(tmp_path):
    result = DockerCommandRunner(sys.executable).run(
        ["-c", "import sys; sys.stdout.write('a' * 3000000); sys.stderr.write('b' * 3000000)"],
        timeout=5, log_directory=tmp_path)
    assert result.returncode == 0
    assert len(result.stdout) < 2_100_000 and len(result.stderr) < 2_100_000
    assert "earlier output omitted" in result.stdout
    assert sorted(path.stat().st_size for path in tmp_path.iterdir()) == [3_000_000, 3_000_000]


def test_session_cancellation_closes_container_before_client_and_joins_readers():
    process = subprocess.Popen([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    control = RunControl()
    calls = []

    def remove_container():
        calls.append(process.poll())
        process.terminate()

    session = DockerSession(process, close_callback=remove_container, control=control)
    control.cancel()
    try:
        with pytest.raises(RunCancelled):
            session.wait(timeout=30)
    finally:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: session.close(), range(2)))
    assert calls == [None]
    assert process.poll() is not None
    assert not any(reader.is_alive() for reader in session._readers)


def test_trace_wait_checks_cancellation_without_waiting_for_timeout():
    control = RunControl()
    control.cancel()
    with pytest.raises(RunCancelled):
        InterceptionTraceState().wait_for_completion_after(0, timeout=30, control=control)


@pytest.mark.parametrize("phase", ["generate", "execute", "late_drain"])
def test_trace_persistence_failure_is_suite_fatal_and_cleanup_still_runs(phase):
    process = subprocess.Popen([sys.executable, "-c", "print('done')"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    state = InterceptionTraceState()
    cleaned = []
    session = DockerSession(
        process, close_callback=lambda: cleaned.append(True),
        runtime_error_checker=state.check_persistence,
        trace_validator=(lambda checkpoint: state.wait_for_completion_after(checkpoint, 1))
                        if phase == "execute" else None,
    )
    if phase == "late_drain":
        assert session.wait(timeout=3) == 0
    state.fail(OSError("evidence disk unavailable"))
    try:
        if phase != "late_drain":
            with pytest.raises(RuntimeInfrastructureError, match="evidence disk"):
                session.wait(timeout=3)
    finally:
        with pytest.raises(RuntimeInfrastructureError, match="evidence disk"):
            session.close()
    assert cleaned == [True]
    assert not any(reader.is_alive() for reader in session._readers)


def test_docker_client_environment_is_frozen_for_commands_and_suite_workers(monkeypatch):
    monkeypatch.setenv("ABB_DOCKER_SNAPSHOT_TEST", "initial")
    commands = DockerCommandRunner(sys.executable)
    services = RuntimeServices(environ={"DOCKER_CONTEXT": "fixed-context"})
    monkeypatch.setenv("ABB_DOCKER_SNAPSHOT_TEST", "mutated")
    monkeypatch.setenv("DOCKER_CONTEXT", "wrong-context")
    monkeypatch.setenv("ABB_DOCKER_LATE_TEST", "must-not-appear")
    result = commands.run(["-c", "import os; print(os.environ['ABB_DOCKER_SNAPSHOT_TEST'])"], timeout=3)
    assert result.stdout.strip() == "initial"
    runtime = services.create_docker_runtime()
    assert runtime._commands.environ["DOCKER_CONTEXT"] == "fixed-context"
    assert runtime._commands.environ["ABB_DOCKER_SNAPSHOT_TEST"] == "initial"
    assert "ABB_DOCKER_LATE_TEST" not in runtime._commands.environ
    assert "PATH" in runtime._commands.environ  # Partial Agent env callers remain supported.


def test_builder_fingerprint_is_stable_across_staging_paths_and_changes_with_dockerfile(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        root.mkdir()
        (root / "Dockerfile").write_text("FROM python:3.11-slim\n")
        (root / "main.py").write_text("print('agent')\n")
    assert _content_digest(first) == _content_digest(second)
    (second / "Dockerfile").write_text("FROM python:3.12-slim\n")
    assert _content_digest(first) != _content_digest(second)


def test_builder_cached_label_must_match_full_fingerprint(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    commands = SimpleNamespace(run=lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "wrong", ""))
    builder = DockerImageBuilder(command_runner=commands)
    with pytest.raises(DockerBuildError, match="fingerprint"):
        builder.build(context=tmp_path, dockerfile=tmp_path / "Dockerfile", repository="agent")


@pytest.fixture
def fake_agent_runtime(tmp_path, monkeypatch):
    import agentbench.runtime.docker.runtime as module
    control = RunControl()
    services = RuntimeServices(environ={})
    runtime = services.create_docker_runtime(control=control, run_id="artifact-1",
                                             identity={"suite_id": "suite-1", "job_id": "job-1"})
    config = SimpleNamespace(build_context=tmp_path, dockerfile=tmp_path / "Dockerfile",
                             agent_id="test-agent", environment={}, workdir="/app",
                             argv=["echo", "test"], timeout_sec=3)
    monkeypatch.setattr(module.AgentContainerConfig, "from_agent_dir", lambda *args, **kwargs: config)
    monkeypatch.setattr(module.InterceptionConfig, "from_agent_dir", lambda *args, **kwargs: None)
    runtime._images = SimpleNamespace(build=lambda **kwargs: "image:cached")
    return runtime, control, services, SimpleNamespace(path=tmp_path)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_creation_cancel_race_cleans_planned_names_and_retains_cleanup_failure(fake_agent_runtime, cleanup_fails):
    runtime, control, services, agent = fake_agent_runtime
    calls = []

    def command(args, **kwargs):
        calls.append((list(args), kwargs))
        if args[0] == "create":
            # Docker created the resource, but cancellation reached the caller
            # before a session/created response could be returned.
            control.cancel()
            raise RunCancelled("cancel after create")
        if cleanup_fails and args[:2] == ["container", "rm"]:
            return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")
        return subprocess.CompletedProcess(args, 0, "created-id", "")

    runtime._commands = SimpleNamespace(run=command)
    with pytest.raises(DockerCleanupError if cleanup_fails else RunCancelled):
        runtime.start(agent)
    resources = services.resource_registry.snapshot()
    assert len(resources) == 2
    assert {item["identity"]["role"] for item in resources} == {"network", "agent"}
    assert {item["identity"]["suite_id"] for item in resources} == {"suite-1"}
    for args, kwargs in calls:
        if "rm" in args:
            assert kwargs["cleanup"] is True
            assert kwargs["deadline"].remaining() >= 0
    assert any(args[:2] == ["network", "rm"] for args, _ in calls)
    if cleanup_fails:
        assert any(item["status"] == "cleanup_failed" for item in resources)
        with pytest.raises(DockerCleanupError):
            services.close()
    else:
        assert all(item["status"] == "removed" for item in resources)
        services.close()


def test_runtime_services_share_builds_but_not_sessions_or_environment():
    services = RuntimeServices(environ={"MODEL": "original"})
    first = services.create_docker_runtime()
    second = services.create_docker_runtime()
    assert first is not second
    assert first._images.coordinator is second._images.coordinator is services.build_coordinator
    assert first._resources is second._resources is services.resource_registry
    first._environ["MODEL"] = "changed"
    assert second._environ["MODEL"] == services.environ["MODEL"] == "original"
    assert RuntimeServices().build_coordinator is not services.build_coordinator


def test_start_uses_one_preparation_deadline_for_every_command(fake_agent_runtime):
    runtime, control, services, agent = fake_agent_runtime
    deadline = Deadline.after(5)
    seen = []

    def command(args, **kwargs):
        if kwargs.get("cleanup"):
            return subprocess.CompletedProcess(args, 0, "removed", "")
        seen.append(kwargs["deadline"])
        if args[0] == "create":
            raise RuntimeError("controlled end of preparation")
        return subprocess.CompletedProcess(args, 0, "id", "")

    runtime._commands = SimpleNamespace(run=command)
    with pytest.raises(RuntimeError, match="controlled end"):
        runtime.start(agent, preparation_deadline=deadline)
    assert len(seen) == 3 and all(value is deadline for value in seen)
    services.close()


def test_interrupted_creation_with_unknown_daemon_state_does_not_claim_cleanup_success(fake_agent_runtime):
    runtime, control, services, agent = fake_agent_runtime

    def command(args, **kwargs):
        if args[0] == "create":
            error = RunCancelled("Docker client was still running at cancellation")
            error.docker_client_interrupted = True
            control.cancel()
            raise error
        if args[:2] == ["container", "rm"]:
            return subprocess.CompletedProcess(args, 1, "", "No such container")
        return subprocess.CompletedProcess(args, 0, "id", "")

    runtime._commands = SimpleNamespace(run=command)
    with pytest.raises(DockerCleanupError, match="delayed create"):
        runtime.start(agent)
    assert any(item["status"] == "cleanup_failed" for item in services.resource_registry.snapshot())
