"""Issue #65: the evaluation overlay installs the SDK even when the image's python has no pip."""
import os
import shutil
import subprocess
import textwrap

import pytest

from agentbench.sdk.plugin.kuma.image import SDK_INSTALL, evaluation_agent
from tests.test_kuma_requirement import unit  # noqa: F401 - pytest fixture

FAKE_PYTHON = textwrap.dedent('''\
    #!/bin/sh
    # Stand-in interpreter: its pip/ensurepip availability comes from marker files.
    echo "$*" >> "$STATE/calls"
    if [ "$1" != "-m" ]; then exit 2; fi
    case "$2" in
      pip)
        if [ ! -f "$STATE/pip" ]; then echo "$0: No module named pip" >&2; exit 1; fi
        exit 0 ;;
      ensurepip)
        if [ ! -f "$STATE/ensurepip" ]; then echo "$0: No module named ensurepip" >&2; exit 1; fi
        touch "$STATE/pip"; exit 0 ;;
    esac
    exit 2
''')


def _run_install_step(tmp_path, *, pip, ensurepip):
    if shutil.which('sh') is None:
        pytest.skip('POSIX shell required')
    state, bin_dir = tmp_path / 'state', tmp_path / 'venv' / 'bin'
    state.mkdir()
    bin_dir.mkdir(parents=True)
    python = bin_dir / 'python'
    python.write_text(FAKE_PYTHON)
    python.chmod(0o755)
    for name, present in (('pip', pip), ('ensurepip', ensurepip)):
        if present:
            (state / name).touch()
    assert SDK_INSTALL.startswith('RUN ') and SDK_INSTALL.endswith('\n')
    completed = subprocess.run(
        ['sh', '-c', SDK_INSTALL[len('RUN '):]], capture_output=True, text=True, timeout=30,
        env={'PATH': f'{bin_dir}:/usr/bin:/bin', 'STATE': str(state)})
    calls = (state / 'calls').read_text().splitlines() if (state / 'calls').exists() else []
    return completed, calls, python


def test_python_with_pip_installs_directly(tmp_path):
    completed, calls, _ = _run_install_step(tmp_path, pip=True, ensurepip=False)
    assert completed.returncode == 0, completed.stderr
    assert not any(call.startswith('-m ensurepip') for call in calls)
    assert calls[-1].startswith('-m pip --isolated install') and '/opt/abb-sdk/requirements.txt' in calls[-1]


def test_uv_style_venv_without_pip_is_bootstrapped_with_ensurepip(tmp_path):
    completed, calls, _ = _run_install_step(tmp_path, pip=False, ensurepip=True)
    assert completed.returncode == 0, completed.stderr
    assert calls[0] == '-m pip --version'
    assert calls[1] == '-m ensurepip --default-pip'
    assert calls[-1].startswith('-m pip --isolated install')


def test_interpreter_without_pip_or_ensurepip_is_named(tmp_path):
    completed, calls, python = _run_install_step(tmp_path, pip=False, ensurepip=False)
    assert completed.returncode == 1
    assert f'{python} has no pip module and no ensurepip' in completed.stderr
    assert not any(call.startswith('-m pip --isolated install') for call in calls)


def test_overlay_uses_the_bootstrapping_install_step(unit):  # noqa: F811 - pytest fixture
    agent = type('Agent', (), {'path': unit, 'agent_id': 'requirement-test', 'framework': 'fixture'})()
    with evaluation_agent(agent) as staged:
        dockerfile = (staged.path / 'Dockerfile').read_text()
    assert SDK_INSTALL in dockerfile
    assert dockerfile.index('USER root') < dockerfile.index(SDK_INSTALL) < dockerfile.rindex('USER agent')
    assert os.linesep not in SDK_INSTALL[:-1]  # One Dockerfile instruction.
