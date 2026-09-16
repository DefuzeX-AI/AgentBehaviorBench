"""Bindings must reach the runtime stage, not merely exist in the build context."""

from types import SimpleNamespace

import pytest

from agentbench.onboarding.build_agent_env.build_dockerfile.service import validate
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, FILES, MANIFEST, write


def check(source, content):
    write(source.directory, "agent.toml", MANIFEST)
    write(source.directory, "bindings/bridge.py", FILES["bindings/bridge.py"])
    validate(content + "\nUSER agent\n", SimpleNamespace(source=source))


@pytest.mark.parametrize("copy", [
    "COPY bindings/ ./bindings/",
    'COPY --chown=10001:10001 ["bindings/", "./bindings/"]',
    "COPY bindings/bridge.py /opt/agent/bindings/bridge.py",
    "COPY bindings/*.py /opt/agent/bindings/",
    "COPY . /opt/agent/",
])
def test_directory_file_json_and_wildcard_copies_retain_binding(source, copy):
    check(source, "FROM python:3.11-slim\nWORKDIR /opt/agent\n" + copy)


@pytest.mark.parametrize("copy", ["", "COPY bindings/ ./agent/bindings/", "COPY bindings/ /tmp/bindings/"])
def test_absent_or_wrong_destination_is_rejected(source, copy):
    with pytest.raises(BuildError, match="final runtime image"):
        check(source, "FROM python:3.11-slim\nWORKDIR /opt/agent\n" + copy)


def test_copy_in_discarded_builder_does_not_satisfy_runtime_image(source):
    with pytest.raises(BuildError, match="final runtime image"):
        check(source, """FROM python:3.11-slim AS builder
WORKDIR /opt/agent
COPY bindings/ ./bindings/
FROM python:3.11-slim
WORKDIR /opt/agent
""")


@pytest.mark.parametrize("stage", ["builder", "0"])
def test_multistage_copy_transfers_binding_to_runtime(source, stage):
    check(source, f"""FROM python:3.11-slim AS builder
COPY bindings/ /prepared/bindings/
FROM python:3.11-slim
WORKDIR /opt/agent
COPY --from={stage} /prepared/ ./
""")


def test_named_base_stage_inherits_binding_and_workdir(source):
    check(source, """FROM python:3.11-slim AS prepared
WORKDIR /opt/agent
COPY bindings/ ./bindings/
FROM prepared AS runtime
""")


def test_docker_instruction_whitespace_does_not_hide_bindings(source):
    check(source, "FROM\tpython:3.11-slim\nWORKDIR\t/opt/agent\nCOPY\tbindings/ ./bindings/\n")


def test_file_named_bridge_is_not_the_selected_binding(source):
    write(source.directory, "agent/bridge.py", "unrelated")
    with pytest.raises(BuildError, match="final runtime image"):
        check(source, "FROM python:3.11-slim\nCOPY agent/bridge.py /opt/agent/bindings/bridge.py")
