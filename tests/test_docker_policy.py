"""Opt-in filesystem acceptance using an existing non-root Python Agent image."""
import os
import subprocess
from uuid import uuid4

import pytest

from agentbench.runtime.docker.policy import DockerPolicy


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
