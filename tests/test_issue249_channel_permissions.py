"""The isolated controller and Agent share only their request/response channel."""

import asyncio
import json
from agentbench.runtime.docker.execution_policy import ControllerExecutionPolicy
from agentbench.sdk.integration.context import ExecutionChannel
from agentbench.sdk.integration import channel as controller_channel
from agentbench.runtime.agentcontainer import channel as agent_channel


def test_controller_requests_shared_permissions_for_agent_channel(tmp_path):
    channel = ExecutionChannel.create(tmp_path / 'channel')
    policy = ControllerExecutionPolicy(
        tmp_path / 'storage', repository=tmp_path / 'workspace', channel=channel)

    assert set(policy.shared_directories()) == {channel.requests, channel.responses}


def test_agent_reclaims_response_only_after_controller_removes_request(tmp_path, monkeypatch):
    class Session:
        async def aclose(self):
            pass

        def snapshot(self):
            return {'invocations': 1, 'closed': False}

    async def execute(root, request, output, **kwargs):
        (output / 'result.json').write_text('{}', encoding='utf-8')
        return 0

    monkeypatch.setattr(agent_channel, 'AgentSession', Session)
    monkeypatch.setattr(agent_channel, 'execute', execute)
    requests, responses = tmp_path / 'request', tmp_path / 'response'
    requests.mkdir()
    responses.mkdir()

    async def wait_until(predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError('channel did not reach the expected state')

    async def exercise():
        server = asyncio.create_task(agent_channel.serve(
            root=tmp_path, requests=requests, responses=responses))
        request = requests / '00000000.json'
        request.write_text(json.dumps({'operation': 'invoke'}), encoding='utf-8')
        response = responses / '00000000'
        await wait_until(lambda: (response / 'done.json').is_file())
        assert response.is_dir()
        request.unlink()
        await wait_until(lambda: not response.exists())

        close_request = requests / '00000001.json'
        close_request.write_text(json.dumps({'operation': 'close'}), encoding='utf-8')
        close_response = responses / '00000001'
        await wait_until(lambda: (close_response / 'done.json').is_file())
        close_request.unlink()
        await asyncio.wait_for(server, timeout=3)
        assert not close_response.exists()

    asyncio.run(exercise())


def test_controller_releases_response_when_copy_fails(tmp_path, monkeypatch):
    requests, responses = tmp_path / 'requests', tmp_path / 'responses'
    requests.mkdir()
    responses.mkdir()
    response = responses / '00000000'
    response.mkdir()
    (response / 'done.json').write_text(json.dumps({
        'sequence': 0,
        'session': {'invocations': 1, 'closed': False},
    }), encoding='utf-8')
    session = controller_channel.DirectoryAgentSession(
        requests=requests, responses=responses)

    def fail_copy(*_args, **_kwargs):
        raise ValueError('fixture response rejected')

    monkeypatch.setattr(controller_channel, 'collect_response', fail_copy)

    try:
        asyncio.run(session.invoke({'run_id': 'failed-copy'}, tmp_path / 'output', None))
    except ValueError as exc:
        assert str(exc) == 'fixture response rejected'
    else:
        raise AssertionError('Expected response collection to fail')

    assert not (requests / '00000000.json').exists()
