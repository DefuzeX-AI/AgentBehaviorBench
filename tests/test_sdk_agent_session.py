"""SDK-independent session ownership keeps invocation artifacts and cleanup intact."""
import asyncio
import json

import pytest

from agentbench.sdk.integration.agent import LocalAgentSession, ManagedAgentSession


class RecordingSession:
    def __init__(self, *, error=None, close_error=None):
        self.requests = []
        self.error = error
        self.close_error = close_error
        self.closes = 0

    async def invoke(self, envelope, output):
        self.requests.append(envelope)
        if self.error is not None:
            raise self.error
        return {'run_id': envelope['run_id'], 'status': 'succeeded', 'output': envelope['input']}

    async def aclose(self):
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error

    def snapshot(self):
        return {'invocations': len(self.requests), 'closed': self.closes > 0}


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


def test_injected_session_preserves_multiturn_envelopes(tmp_path):
    session, replay = RecordingSession(), Replay()

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session, replay=replay) as managed:
            for index in (1, 2):
                folder = tmp_path / 'inputs' / str(index)
                result = await managed.invoke(request(index), folder)
                assert result == json.loads((folder / 'result.json').read_text())
                assert result['output'] == f'current {index}'
                assert json.loads((folder / 'request.json').read_text()) == request(index)
        await managed.aclose()  # No duplicate close or replay finalization.
        with pytest.raises(RuntimeError, match='closed'):
            await managed.invoke(request(3), tmp_path / 'inputs' / '3')

    asyncio.run(execute())
    assert session.requests == [request(1), request(2)]
    assert session.closes == 1
    assert replay.events == [('input_start', 'input-1'), ('input_end', 'input-1'),
                             ('input_start', 'input-2'), ('input_end', 'input-2'), 'finished']
    assert json.loads((tmp_path / 'session.json').read_text()) == {'invocations': 2, 'closed': True}


@pytest.mark.parametrize('error', [RuntimeError('Agent failed'), asyncio.CancelledError()])
def test_failure_and_cancellation_close_session_and_finish_replay(tmp_path, error):
    session, replay = RecordingSession(error=error), Replay()

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session, replay=replay) as managed:
            await managed.invoke(request(1), tmp_path / 'inputs' / '1')

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


def test_local_session_runs_agent_in_process_with_one_native_session(tmp_path):
    calls = []

    async def worker(root, request_path, output, *, session):
        envelope = json.loads(request_path.read_text())
        calls.append((root, envelope['input'], session))
        (output / 'result.json').write_text(json.dumps(
            {'run_id': envelope['run_id'], 'status': 'succeeded', 'output': envelope['input']}))

    local = LocalAgentSession(tmp_path / 'unit', capture_directory=tmp_path / 'otel', invoke=worker)

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=local) as managed:
            for index in (1, 2):
                folder = tmp_path / 'inputs' / str(index)
                result = await managed.invoke(request(index), folder)
                assert result['output'] == f'current {index}'
                assert sorted(path.name for path in folder.iterdir()) == ['request.json', 'result.json']
            with pytest.raises(ValueError):
                await managed.invoke(request(3), tmp_path.parent / 'outside-output')

    asyncio.run(execute())
    assert [call[1] for call in calls] == ['current 1', 'current 2']
    assert calls[0][0] == tmp_path / 'unit'
    assert calls[0][2] is calls[1][2]  # One native Agent session serves the whole Case.
    assert local.session.capture_directory == tmp_path / 'otel'
    assert local.closed


def test_local_session_rejects_a_result_from_another_invocation(tmp_path):
    async def worker(root, request_path, output, *, session):
        (output / 'result.json').write_text(json.dumps({'run_id': 'someone-else', 'status': 'succeeded'}))

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=LocalAgentSession(
                tmp_path / 'unit', invoke=worker)) as managed:
            await managed.invoke(request(1), tmp_path / 'inputs' / '1')

    with pytest.raises(ValueError, match='different invocation'):
        asyncio.run(execute())


def test_invocation_artifacts_and_returned_outputs_are_redacted(tmp_path, monkeypatch):
    secret = 'sk-sdk-session-fixture-secret-123456'
    monkeypatch.setenv('OPENAI_API_KEY', secret)
    session = RecordingSession()
    envelope = {**request(1), 'input': f'Hello {secret}'}

    async def execute():
        async with ManagedAgentSession(output=tmp_path, session=session) as managed:
            result = await managed.invoke(envelope, tmp_path / 'inputs' / '1')
            assert secret not in json.dumps(result)

    asyncio.run(execute())
    assert secret not in json.dumps(session.requests)
    assert secret not in (tmp_path / 'inputs' / '1' / 'request.json').read_text()


def test_production_worker_executes_the_agent_in_its_own_container(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import worker

    settings = tmp_path / 'evaluation.json'
    settings.write_text(json.dumps({'mode': 'execute'}))
    modes = []

    async def execute(root, output, settings, **kwargs):
        modes.append(settings['mode'])
        return 0

    monkeypatch.setattr(worker, 'share_output', lambda path: None)
    monkeypatch.setattr(worker, 'execute', execute)
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(tmp_path)])
    assert worker.main() == 0
    assert modes == ['execute']
    assert not (tmp_path / 'error.json').exists()
