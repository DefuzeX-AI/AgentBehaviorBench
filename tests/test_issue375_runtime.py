"""Real process/timeout regressions; no model or paid service calls."""
import os
from pathlib import Path
import signal
import subprocess
import time
from types import SimpleNamespace
import pytest
from tests.test_issue375_decompai import transport, bridge, UNIT


def alive(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip()[:1] not in ('', 'Z')


def remove_child(path):
    if path.exists():
        try: os.kill(int(path.read_text()), signal.SIGKILL)
        except ProcessLookupError: pass


def test_persistent_timeout_retains_actual_output(monkeypatch, tmp_path):
    monkeypatch.setenv('DECOMPAI_TOOL_TIMEOUT', '1')
    process = transport.ContainerBashProcess(persistent=True, workdir=str(tmp_path))
    try:
        with pytest.raises(TimeoutError, match='actual-output-before-timeout'):
            process.run('printf actual-output-before-timeout; sleep 4')
    finally: transport.close_all()


def test_persistent_timeout_kills_descendants(monkeypatch, tmp_path):
    monkeypatch.setenv('DECOMPAI_TOOL_TIMEOUT', '1')
    process = transport.ContainerBashProcess(persistent=True, workdir=str(tmp_path))
    child = tmp_path/'child.pid'
    try:
        with pytest.raises(TimeoutError):
            process.run('sleep 10 & echo $! > child.pid; wait')
        for _ in range(20):
            if not alive(int(child.read_text())): break
            time.sleep(.05)
        assert not alive(int(child.read_text())), 'Timed-out shell left its actual child running'
    finally:
        remove_child(child)
        transport.close_all()


@pytest.mark.parametrize('utility', [False, True])
def test_oneoff_timeout_is_bounded_and_keeps_output(monkeypatch, tmp_path, utility):
    monkeypatch.setenv('DECOMPAI_TOOL_TIMEOUT', '1')
    monkeypatch.setenv('DECOMPAI_ANALYSIS_TIMEOUT', '1')
    command = f'cd {tmp_path}; sleep 4 & echo $! > child.pid; printf actual-partial-output; wait'
    child = tmp_path/'child.pid'
    class Result:
        def __init__(self, stdout, stderr, combined): pass
    utils = SimpleNamespace(CommandResult=Result)
    transport.install(utils, SimpleNamespace())
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='actual-partial-output'):
            if utility: utils.run_command_in_docker(command)
            else: transport.ContainerBashProcess(workdir=str(tmp_path)).run(command)
        assert time.monotonic()-started < 3, 'A child kept timeout pipes open past the limit'
        assert not alive(int(child.read_text()))
    finally:
        remove_child(child)
        transport.close_all()


def test_new_default_budget_allows_sixteen_native_steps(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    monkeypatch.delenv('DECOMPAI_MAX_CALLS', raising=False)
    monkeypatch.syspath_prepend(str(UNIT/'bindings'))
    monkeypatch.setattr(bridge,'parse_input',lambda value:('independent offline input',tmp_path/'binary'))
    monkeypatch.setattr(bridge,'upstream_system_prompt',lambda:'unaltered native prompt fixture')
    recorded = {}
    class Graph:
        async def ainvoke(self, state, config, **kwargs):
            recorded.update(config)
            budget = next(h for h in config['callbacks'] if hasattr(h,'exceeded'))
            for _ in range(16): budget.on_chat_model_start(None,None)
            return {'messages':[AIMessage(content='native terminal response fixture')]}
    native=SimpleNamespace(utils=SimpleNamespace(create_session_for_binary=lambda p:str(tmp_path)),graph=Graph(),model_context_length=128000)
    monkeypatch.setattr(bridge,'_native',lambda:native)
    result=bridge.create_graph().invoke('input')
    assert result['model_calls']==16
    assert result['answer']=='native terminal response fixture'
    assert recorded['recursion_limit']==40


@pytest.mark.parametrize('count', ['0', '3', '100'])
def test_generation_batch_size_rejected_before_profile_or_sdk(count):
    import sys
    result=subprocess.run([sys.executable,str(UNIT/'validation/generate_official.py'),
        '--profile','/missing-profile','--profile-sha256','0'*64,
        '--environment','/missing-environment','--repo','/missing-repo',
        '--output','/missing-output','--count',count],capture_output=True,text=True)
    assert result.returncode==2
    assert 'invalid choice' in result.stderr
