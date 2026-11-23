"""Controller cleanup must allow a valid ACP close acknowledgement, without LLMs."""
import asyncio
from types import SimpleNamespace
import pytest
from agentbench.observe.store import atomic_json
from agentbench.sdk.integration import channel


def test_valid_cleanup_ack_after_twelve_seconds_is_not_cut_off(tmp_path, monkeypatch):
    requests = tmp_path / 'requests'; responses = tmp_path / 'responses'
    requests.mkdir(); responses.mkdir()
    clock = [0.0]
    real_sleep = asyncio.sleep
    async def progress(seconds):
        clock[0] += seconds
        # This is a controller protocol fixture, not an Agent or model substitute.
        if clock[0] >= 12 and (requests / '00000000.json').is_file():
            (responses / '00000000').mkdir(exist_ok=True)
            atomic_json(responses / '00000000/done.json',
                        {'sequence': 0, 'session': {'invocations': 1, 'closed': True}})
        await real_sleep(0)
    monkeypatch.setattr(channel, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(channel, 'asyncio', SimpleNamespace(sleep=progress))
    session = channel.DirectoryAgentSession(timeout=240, requests=requests, responses=responses)
    asyncio.run(session.aclose())
    assert session.snapshot()['closed'] is True
    assert clock[0] >= 12 and clock[0] < 14
    assert not (requests / '00000000.json').exists()


@pytest.mark.parametrize('runtime_timeout,expected', [(4, 4), (60, 60), (240, 60)])
def test_cleanup_wait_stays_bounded_by_runtime_timeout(runtime_timeout, expected):
    session = channel.DirectoryAgentSession(timeout=runtime_timeout)
    calls = []
    async def exchange(envelope, timeout):
        calls.append((envelope, timeout))
    session._exchange = exchange
    asyncio.run(session.aclose())
    assert calls == [({'operation': 'close'}, expected)]


def test_never_acknowledged_close_still_times_out(tmp_path, monkeypatch):
    requests = tmp_path / 'requests'; responses = tmp_path / 'responses'
    requests.mkdir(); responses.mkdir(); clock = [0.0]; real_sleep = asyncio.sleep
    async def progress(seconds):
        clock[0] += seconds
        await real_sleep(0)
    monkeypatch.setattr(channel, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(channel, 'asyncio', SimpleNamespace(sleep=progress))
    session = channel.DirectoryAgentSession(timeout=2, requests=requests, responses=responses)
    with pytest.raises(TimeoutError, match='did not complete'):
        asyncio.run(session.aclose())
    assert 2 <= clock[0] < 3
