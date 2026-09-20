"""Real subprocess tests for ACP ownership, not mocked protocol method calls."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
import sys
import time

import pytest

pytest.importorskip('acp')
from agentbench.adapter.acp import ACPAdapter
from agentbench.adapter.acp.config import ACPConfig
from agentbench.adapter.acp.errors import ACPError
from agentbench.adapter.acp.process import child_environment

SERVER = Path(__file__).parent / 'acp_fixtures/server.py'


@pytest.fixture
def adapter(tmp_path):
    value = ACPAdapter(ACPConfig(tmp_path, (sys.executable, str(SERVER)), str(tmp_path),
                                timeout=2, handshake_timeout=2, cleanup_timeout=0.3))
    yield value
    value.close()


def test_sync_turns_reuse_session_and_do_not_replay_history(adapter):
    first = adapter.invoke('first')
    second = adapter.invoke('second')
    assert first.output == '1:first' and second.output == '2:second'
    assert first.raw_output['session_id'] == second.raw_output['session_id']
    assert first.raw_output['pid'] == second.raw_output['pid']
    pid = second.raw_output['pid']
    adapter.close()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not adapter.is_loaded
    adapter.close()


def test_async_inputs_reuse_session_and_support_sync_caller(adapter):
    async def call():
        return await adapter.ainvoke('async')
    result = asyncio.run(call())
    assert result.output == '1:async'
    assert adapter.invoke('sync').output == '2:sync'


def test_two_cases_have_independent_process_and_history(adapter):
    other = ACPAdapter(adapter.config)
    try:
        first, second = adapter.invoke('A'), other.invoke('B')
        assert first.raw_output['session_id'] != second.raw_output['session_id']
        assert first.raw_output['pid'] != second.raw_output['pid']
        assert first.output == '1:A' and second.output == '1:B'
    finally:
        other.close()


@pytest.mark.parametrize('value', ['hang', 'malformed'])
def test_timeout_terminates_agent_and_owned_loop(adapter, value):
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        adapter.invoke(value)
    pid = adapter._session.process.pid
    adapter.close()
    assert time.monotonic() - started < 8
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_disconnect_is_not_success_or_automatic_replay(adapter):
    with pytest.raises(Exception):
        adapter.invoke('disconnect')
    assert adapter._session.closed
    with pytest.raises(ACPError, match='closed'):
        adapter.invoke('later')


def test_authentication_failure_prevents_prompt(adapter):
    adapter.config = replace(adapter.config, auth_method='test')
    with pytest.raises(Exception, match='authentication rejected'):
        adapter.invoke('never sent')
    assert adapter._session.client.session_id is None


def test_unknown_authentication_method_fails_before_prompt(adapter):
    adapter.config = replace(adapter.config, auth_method='missing')
    with pytest.raises(ACPError, match='not advertised'):
        adapter.invoke('never sent')


def test_stderr_is_drained_without_contaminating_answer(adapter):
    assert adapter.invoke('stderr').output == '1:stderr'


def test_reply_limit_cannot_be_mistaken_for_success(adapter):
    adapter.config = replace(adapter.config, max_output_bytes=1024)
    with pytest.raises(ACPError, match='output limit'):
        adapter.invoke('big')


def test_stop_reason_is_not_a_judge_verdict(adapter):
    result = adapter.invoke('refuse')
    assert result.raw_output['stop_reason'] == 'refusal'
    with pytest.raises(ACPError, match='max_tokens'):
        adapter.invoke('limit')


def test_cancel_waits_for_process_cleanup(adapter):
    async def run():
        task = asyncio.create_task(adapter.ainvoke('hang'))
        while not adapter._session or not adapter._session.client.session_id:
            await asyncio.sleep(0.01)
        pid = adapter._session.process.pid
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    asyncio.run(run())


def test_unconfigured_structured_input_is_rejected_before_launch(adapter):
    with pytest.raises(ValueError, match='input_key'):
        adapter.invoke({'task': 'example'})
    assert not adapter.is_loaded
    adapter.config = replace(adapter.config, input_key='task')
    assert adapter.invoke({'task': 'example', 'ignored': 'old history'}).output == '1:example'


def test_agent_environment_only_includes_declared_credentials(adapter, monkeypatch):
    monkeypatch.setenv('KUMA_API_KEY', 'test-sdk-key')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-agent-key')
    monkeypatch.setenv('NODE_EXTRA_CA_CERTS', '/test/ca.pem')
    env = child_environment(replace(adapter.config, env_keys=('ANTHROPIC_API_KEY',)))
    assert env['ANTHROPIC_API_KEY'] == 'test-agent-key'
    assert env['NODE_EXTRA_CA_CERTS'] == '/test/ca.pem'
    assert 'KUMA_API_KEY' not in env


def test_concurrent_prompts_are_rejected_without_poisoning_active_session(adapter):
    async def run():
        task = asyncio.create_task(adapter.ainvoke('hang'))
        while not adapter._session or not adapter._session.client.session_id:
            await asyncio.sleep(0.01)
        with pytest.raises(ACPError, match='already active'):
            await adapter.ainvoke('overlap')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())


def test_cleanup_terminates_agent_descendants(adapter):
    child = int(adapter.invoke('child').output)
    adapter.close()
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    pytest.fail('Agent descendant survived process group cleanup')
