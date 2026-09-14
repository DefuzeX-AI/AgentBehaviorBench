"""Issue #14: even a stuck kill/wait cleanup must not disclose Docker env argv."""
import subprocess
import traceback

import pytest

from agentbench.runtime.docker.command import DockerCommandRunner


def test_cleanup_timeout_redacts_exception_and_traceback():
    secret = 'synthetic-issue14-secret'

    class StuckProcess:
        args = ['docker', 'create', '--env', f'EXAMPLE_API_KEY={secret}']

        def poll(self): return None
        def terminate(self): pass
        def kill(self): pass
        def wait(self, timeout=None): raise subprocess.TimeoutExpired(self.args, timeout)

    with pytest.raises(TimeoutError) as caught:
        DockerCommandRunner.terminate(StuckProcess())
    rendered = ''.join(traceback.format_exception(caught.value))
    assert secret not in str(caught.value)
    assert secret not in rendered
    assert 'EXAMPLE_API_KEY=' not in str(caught.value)
