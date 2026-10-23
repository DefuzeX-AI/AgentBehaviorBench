"""ACP callbacks keep directories they create removable by the host user."""
import asyncio
import os
import stat

import pytest

pytest.importorskip('acp')
from agentbench.adapter.acp.config import ACPConfig
from agentbench.adapter.acp.filesystem import write_file
from agentbench.adapter.acp.terminal import Terminals

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX permission bits')


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_terminal_commands_create_open_directories(tmp_path):
    async def run():
        config = ACPConfig(tmp_path, ('test',), str(tmp_path))
        terminals = Terminals(config, lambda *args: None)
        previous = os.umask(0o022)
        try:
            created = await terminals.create('/bin/sh', ['-c', 'mkdir -p made/nested && echo x > made/nested/f'])
        finally:
            os.umask(previous)
        await terminals.wait(created.terminal_id)
        await terminals.release(created.terminal_id)
    asyncio.run(run())
    assert _mode(tmp_path / 'made') == 0o777
    assert _mode(tmp_path / 'made/nested') == 0o777


def test_write_file_creates_open_parent_directories(tmp_path):
    config = ACPConfig(tmp_path, ('test',), str(tmp_path), max_output_bytes=1024)
    previous = os.umask(0o022)
    try:
        write_file(config, str(tmp_path / 'a/b/c.txt'), 'x')
    finally:
        os.umask(previous)
    assert (tmp_path / 'a/b/c.txt').read_text() == 'x'
    assert _mode(tmp_path / 'a') == 0o777
    assert _mode(tmp_path / 'a/b') == 0o777
