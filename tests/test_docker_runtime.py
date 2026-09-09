import subprocess
import sys

from agentbench.runtime.docker.session import DockerSession

from agentbench.runtime.docker import DockerPolicy


def test_docker_policy_contains_required_isolation_controls() -> None:
    arguments = DockerPolicy().run_arguments()

    assert "--read-only" in arguments
    assert "--cap-drop=ALL" in arguments
    assert "--security-opt=no-new-privileges" in arguments
    assert any(value.startswith("--memory=") for value in arguments)
    assert any(value.startswith("--cpus=") for value in arguments)
    assert any(value.startswith("--pids-limit=") for value in arguments)
    assert any(value.startswith("--tmpfs=/tmp:rw,") for value in arguments)
    assert any("noexec" in value for value in arguments if value.startswith("--tmpfs=/tmp:"))
    assert any(
        value.startswith("--tmpfs=/run/agentbench-tools:rw,")
        and "exec" in value
        and "noexec" not in value
        for value in arguments
    )



def test_session_captures_free_form_logs_without_stdin_or_invocation_contract():
    process = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys; print('Service started'); print('<html>plain output</html>'); "
         "print('diagnostic', file=sys.stderr)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    cleaned = []
    with DockerSession(process, close_callback=lambda: cleaned.append(True)) as session:
        assert session.wait(timeout=5) == 0
        assert 'Service started' in session.stdout
        assert '<html>plain output</html>' in session.stdout
        assert 'diagnostic' in session.stderr
        assert not hasattr(session, 'invoke')
    session.close()
    assert cleaned == [True]


def test_session_closes_a_persistent_process():
    process = subprocess.Popen(
        [sys.executable, '-u', '-c', 'import time; time.sleep(30)'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    with DockerSession(process, close_callback=lambda: None) as session:
        assert session.is_running
    assert not session.is_running
    assert session.returncode is not None
