"""Issue #116: interceptor bind mounts must be visible to macOS Docker VMs."""

import json
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.runtime.docker.runtime import DockerRuntime
from agentbench.runtime.interception import InterceptionTraceState
from agentbench.runtime.interception.config import CredentialConfig
from agentbench.runtime.interception.providers import ModelTargetConfig


@pytest.fixture
def macos_paths(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    unshared = tmp_path / "private" / "var" / "tmp"
    unshared.mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(tempfile, "tempdir", str(unshared))
    return home, unshared


@pytest.fixture
def interceptor_runtime(tmp_path, monkeypatch):
    runtime = DockerRuntime(
        environ={}, artifact_root=tmp_path / "artifacts",
        interceptor_image_provider=SimpleNamespace(resolve_image=lambda: "interceptor-image"),
    )
    commands = []
    monkeypatch.setattr(runtime, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "_create_resource", lambda kind, name, command, **kwargs: commands.append(command))
    monkeypatch.setattr(runtime, "_remove_resource", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime._commands, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "_follow_trace", lambda *args: (None, None))

    def export_ca(name, destination, **kwargs):
        destination.write_text("test certificate", encoding="utf-8")

    monkeypatch.setattr(runtime, "_wait_for_interceptor", export_ca)
    return runtime, commands


def start_interceptor(runtime, suffix="test", *, mode="observe", credentials=()):
    interception = SimpleNamespace(
        mode=mode, observation_headers={}, observation_tool_purposes={},
        routes=(), tool_routes=(), token_counting={}, credentials=credentials,
    )
    return runtime._start_interceptor(
        agent_id="agent", interception=interception, suffix=suffix,
        network_name="test-network", trace_state=InterceptionTraceState(),
    )[0]


def config_mount(command):
    mount = next(arg for arg in command if "target=/run/secrets/interceptor_config" in arg)
    fields = dict(field.split("=", 1) for field in mount.split(",") if "=" in field)
    assert fields["type"] == "bind" and mount.endswith(",readonly")
    return Path(fields["source"])


def test_macos_interceptor_uses_home_instead_of_unshared_system_temp(macos_paths, interceptor_runtime):
    home, unshared = macos_paths
    runtime, commands = interceptor_runtime
    interceptor = start_interceptor(runtime)
    try:
        config = config_mount(commands[0])
        assert config.is_relative_to(home)
        assert not config.is_relative_to(unshared)
        assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700
        assert json.loads(config.read_text(encoding="utf-8"))["agent_id"] == "agent"
        assert interceptor.ca_certificate.is_relative_to(config.parent)
        assert not runtime.artifact_root.exists()
    finally:
        interceptor.close()
    assert not config.parent.exists()


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_explicit_shared_directory_takes_precedence(platform, macos_paths, interceptor_runtime, monkeypatch, tmp_path):
    runtime, commands = interceptor_runtime
    monkeypatch.setattr(sys, "platform", platform)
    shared = tmp_path / "shared directory" / "interceptors"
    runtime._environ["ABB_DOCKER_TMPDIR"] = str(shared)
    interceptor = start_interceptor(runtime)
    try:
        config = config_mount(commands[0])
        assert config.parent.parent == shared
        assert config.is_file()
        assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700
    finally:
        interceptor.close()
    assert shared.is_dir() and list(shared.iterdir()) == []


def test_live_interceptors_have_separate_directories(macos_paths, interceptor_runtime):
    runtime, commands = interceptor_runtime
    first = start_interceptor(runtime, "first")
    second = None
    try:
        second = start_interceptor(runtime, "second")
        first_config, second_config = map(config_mount, commands)
        assert first_config.parent != second_config.parent
        first.close()
        assert not first_config.parent.exists()
        assert second_config.is_file() and second.ca_certificate.is_file()
    finally:
        first.close()
        if second is not None:
            second.close()
    assert not second_config.parent.exists()


@pytest.mark.parametrize("failure_stage", ["_create_resource", "_wait_for_interceptor"])
def test_startup_failure_removes_private_directory(failure_stage, macos_paths, interceptor_runtime, monkeypatch):
    home, _ = macos_paths
    runtime, _ = interceptor_runtime
    created = []

    def fail(*args, **kwargs):
        created.extend(home.rglob("interceptor_config.json"))
        raise RuntimeError("simulated container startup failure")

    monkeypatch.setattr(runtime, failure_stage, fail)
    with pytest.raises(RuntimeError, match="simulated container startup failure"):
        start_interceptor(runtime)
    assert len(created) == 1
    assert not created[0].parent.exists()


def test_linux_preserves_system_temp_default(macos_paths, interceptor_runtime, monkeypatch):
    _, system_temp = macos_paths
    monkeypatch.setattr(sys, "platform", "linux")
    runtime, commands = interceptor_runtime
    interceptor = start_interceptor(runtime)
    try:
        assert config_mount(commands[0]).parent.parent == system_temp
    finally:
        interceptor.close()


def test_invalid_override_fails_before_container_creation(macos_paths, interceptor_runtime):
    runtime, commands = interceptor_runtime
    runtime._environ["ABB_DOCKER_TMPDIR"] = "relative/path"
    with pytest.raises(ValueError, match="ABB_DOCKER_TMPDIR must be an absolute directory shared with Docker"):
        start_interceptor(runtime)
    assert commands == []


def test_unwritable_override_reports_action_without_fallback(macos_paths, interceptor_runtime, tmp_path):
    _, system_temp = macos_paths
    runtime, commands = interceptor_runtime
    blocked = tmp_path / "file-not-directory"
    blocked.write_text("keep", encoding="utf-8")
    runtime._environ["ABB_DOCKER_TMPDIR"] = str(blocked / "tmp")
    with pytest.raises(OSError, match="set ABB_DOCKER_TMPDIR to a writable absolute directory shared with Docker"):
        start_interceptor(runtime)
    assert commands == [] and list(system_temp.iterdir()) == []
    assert blocked.read_text(encoding="utf-8") == "keep"


def test_replacement_credentials_stay_in_private_readonly_mounts(macos_paths, interceptor_runtime):
    home, _ = macos_paths
    runtime, commands = interceptor_runtime
    target = ModelTargetConfig(
        provider_id="test", target_plugin="openai", base_url="https://example.invalid/v1",
        model="test", credential_env="TEST_API_KEY",
    )
    runtime._model_provider = SimpleNamespace(resolve=lambda environ: target)
    runtime._secret_resolver = SimpleNamespace(require=lambda name: "fixture-only-secret")
    interceptor = start_interceptor(
        runtime, mode="replace", credentials=(CredentialConfig("source", "TEST_API_KEY", "bearer"),),
    )
    try:
        config = config_mount(commands[0])
        paths = {}
        for mount in (arg for arg in commands[0] if arg.startswith("type=bind,")):
            fields = dict(field.split("=", 1) for field in mount.split(",") if "=" in field)
            path = Path(fields["source"])
            assert path.parent == config.parent and path.is_relative_to(home)
            assert mount.endswith(",readonly")
            paths[path.name] = path
        assert set(paths) == {"interceptor_config.json", "source.token", "target.secret"}
        assert paths["target.secret"].read_text(encoding="utf-8") == "fixture-only-secret"
        assert paths["source.token"].read_text(encoding="utf-8")
        assert "fixture-only-secret" not in config.read_text(encoding="utf-8")
        assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700
    finally:
        interceptor.close()
    assert all(not path.exists() for path in paths.values())


def test_configuration_failure_cleans_up_before_container_creation(macos_paths, interceptor_runtime, monkeypatch):
    home, _ = macos_paths
    runtime, commands = interceptor_runtime
    created = []

    def fail(*args, secret_dir, **kwargs):
        created.append(secret_dir)
        (secret_dir / "partial.secret").write_text("fixture-only-secret", encoding="utf-8")
        raise ValueError("simulated configuration failure")

    monkeypatch.setattr("agentbench.runtime.interception.service_config.prepare_service_config", fail)
    with pytest.raises(ValueError, match="simulated configuration failure"):
        start_interceptor(runtime)
    assert len(created) == 1 and created[0].is_relative_to(home)
    assert not created[0].exists() and commands == []
