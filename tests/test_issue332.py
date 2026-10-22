"""Issue #332: a Docker build that exhausts its budget must say so."""

from __future__ import annotations

import subprocess

import pytest

from agentbench.runtime.contracts.execution import RunCancelled, RuntimeInfrastructureError
from agentbench.runtime.docker.command import DockerCommandTimeout
from agentbench.runtime.docker.image_builder import DockerImageBuilder


class _Runner:
    def __init__(self, build_error: BaseException) -> None:
        self.build_error = build_error

    def run(self, args, **kwargs):
        if args[0] == "image":
            return subprocess.CompletedProcess(args, 1, "", "")
        raise self.build_error


def _build(tmp_path, error, timeout=1800):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    builder = DockerImageBuilder(command_runner=_Runner(error), build_timeout=timeout)
    with pytest.raises(RuntimeInfrastructureError) as caught:
        builder.build(context=tmp_path, dockerfile=tmp_path / "Dockerfile", repository="demo")
    return caught.value


def test_build_timeout_names_budget_and_settings(tmp_path):
    error = _build(tmp_path, DockerCommandTimeout("timed out"), timeout=1800)
    message = str(error)
    assert "exceeded its 1800 s build budget" in message
    assert "ABB_RUNTIME_BUILD_TIMEOUT_SEC" in message
    assert "ABB_RUNTIME_PREPARATION_TIMEOUT_SEC" in message
    assert "interrupted" not in message
    assert isinstance(error.__cause__, DockerCommandTimeout)


def test_build_timeout_reports_configured_budget(tmp_path):
    assert "exceeded its 10 s build budget" in str(_build(tmp_path, DockerCommandTimeout(), timeout=10))


def test_cancelled_build_keeps_interrupted_message(tmp_path):
    message = str(_build(tmp_path, RunCancelled("stop")))
    assert "Docker build client interrupted" in message
    assert "build budget" not in message
