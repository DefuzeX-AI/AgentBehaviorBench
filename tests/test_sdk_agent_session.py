"""SDK-independent session ownership keeps original evidence and cleanup intact."""
import asyncio
import json

import pytest

from agentbench.sdk.integration.agent import ManagedAgentSession
from agentbench.sdk.integration.channel import DirectoryAgentSession


class RecordingSession:
    def __init__(self, *, error=None, close_error=None):
        self.requests = []
        self.error = error
        self.close_error = close_error
        self.closes = 0
        self.span = object()

    async def invoke(self, envelope, output, evidence):
        self.requests.append(envelope)
        evidence.accept_span(self.span)
        if self.error is not None:
            raise self.error
        return {'run_id': envelope['run_id'], 'status': 'succeeded', 'output': envelope['input']}

    async def aclose(self):
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error

    def snapshot(self):
        return {'invocations': len(self.requests), 'closed': self.closes > 0}


class Sink:
    def __init__(self):
        self.spans = []

    def accept_span(self, span):
        self.spans.append(span)


class Replay:
    def __init__(self):
        self.events = []

    def checkpoint(self, reason, input_id):
        self.events.append((reason, input_id))

    def finish(self):
        self.events.append('finished')


def request(index):
    return {'schema': 'abb.invocation.v1', 'agent_id': 'echo', 'framework': 'fixture',
            'run_id': f'invocation-{index}', 'session_id': 'one-case', 'input': f'current {index}',
            'observation_context': {'case_id': 'case', 'input_id': f'input-{index}'}}


def test_injected_session_preserves_multiturn_envelopes_and_original_spans(tmp_path):
    session, evidence, replay = RecordingSession(), Sink(), Replay()

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session, replay=replay) as managed:
            for index in (1, 2):
                folder = tmp_path / 'inputs' / str(index)
                result = await managed.invoke(request(index), folder, evidence)
                assert result == json.loads((folder / 'result.json').read_text())
                assert result['output'] == f'current {index}'
                assert json.loads((folder / 'request.json').read_text()) == request(index)
        await managed.aclose()  # No duplicate close or replay finalization.
        with pytest.raises(RuntimeError, match='closed'):
            await managed.invoke(request(3), tmp_path / 'inputs' / '3', evidence)

    asyncio.run(execute())
    assert session.requests == [request(1), request(2)]
    assert evidence.spans == [session.span, session.span]
    assert session.closes == 1
    assert replay.events == [('input_start', 'input-1'), ('input_end', 'input-1'),
                             ('input_start', 'input-2'), ('input_end', 'input-2'), 'finished']
    assert json.loads((tmp_path / 'session.json').read_text()) == {'invocations': 2, 'closed': True}


@pytest.mark.parametrize('error', [RuntimeError('Agent failed'), asyncio.CancelledError()])
def test_failure_and_cancellation_close_session_and_finish_replay(tmp_path, error):
    session, replay = RecordingSession(error=error), Replay()

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session, replay=replay) as managed:
            await managed.invoke(request(1), tmp_path / 'inputs' / '1', Sink())

    with pytest.raises(type(error)):
        asyncio.run(execute())
    assert replay.events == [('input_start', 'input-1'), ('input_end', 'input-1'), 'finished']
    assert session.closes == 1
    assert json.loads((tmp_path / 'session.json').read_text())['closed'] is True


def test_close_failure_still_saves_snapshot_and_finishes_replay(tmp_path):
    session, replay = RecordingSession(close_error=RuntimeError('close failed')), Replay()
    managed = ManagedAgentSession(output=tmp_path, session=session, replay=replay)
    with pytest.raises(RuntimeError, match='close failed'):
        asyncio.run(managed.aclose())
    assert json.loads((tmp_path / 'session.json').read_text())['closed'] is True
    assert replay.events == ['finished']


def test_default_session_uses_host_channel_limits_and_rejects_outside_output(tmp_path):
    managed = ManagedAgentSession(output=tmp_path, settings={
        'agent_timeout': 17, 'agent_response_limits': {'max_bytes': 2000, 'max_files': 10}})
    assert isinstance(managed.session, DirectoryAgentSession)
    assert managed.session.timeout == 17
    assert managed.session.response_limits.max_bytes == 2000
    assert managed.session.response_limits.max_files == 10
    with pytest.raises(ValueError):
        asyncio.run(managed.invoke(request(1), tmp_path.parent / 'outside-output', Sink()))
    assert managed.session.sequence == 0


def test_invocation_artifacts_and_returned_outputs_are_redacted(tmp_path, monkeypatch):
    secret = 'sk-sdk-session-fixture-secret-123456'
    monkeypatch.setenv('OPENAI_API_KEY', secret)
    session = RecordingSession()
    envelope = {**request(1), 'input': f'Hello {secret}'}

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session) as managed:
            result = await managed.invoke(envelope, tmp_path / 'inputs' / '1', Sink())
            assert secret not in json.dumps(result)

    asyncio.run(execute())
    assert secret not in json.dumps(session.requests)
    assert secret not in (tmp_path / 'inputs' / '1' / 'request.json').read_text()


def test_production_worker_requires_isolation_before_session_creation(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import worker

    settings = tmp_path / 'evaluation.json'
    settings.write_text(json.dumps({'mode': 'execute', 'isolated_agent': False}))
    monkeypatch.setattr(worker, 'share_output', lambda path: None)
    monkeypatch.setattr(worker, 'execute', lambda *args, **kwargs: pytest.fail('No local fallback'))
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(tmp_path)])
    assert worker.main() == 1
    error = json.loads((tmp_path / 'error.json').read_text())
    assert error['phase'] == 'startup'
    assert 'requires the isolated Agent channel' in error['message']
