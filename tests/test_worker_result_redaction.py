"""Credentials are removed before the first worker result crosses its boundary."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from agentbench.runtime.agentcontainer.worker import execute


@pytest.mark.parametrize('failure', [False, True])
def test_first_persisted_result_never_contains_runtime_credentials(tmp_path, monkeypatch, failure):
    secret = 'fixture-native-model-credential-12345'
    monkeypatch.setenv('MINIMAX_API_KEY', secret)
    root = tmp_path / 'unit'
    root.mkdir()
    (root / 'agent.toml').write_text('agent_id="fixture"\nframework="acp"\n')
    output = tmp_path / 'output'
    output.mkdir()
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'schema': 'abb.invocation.v1', 'run_id': 'invoke-1',
        'agent_id': 'fixture', 'framework': 'acp', 'input': 'Read the fixture'}))

    class Adapter:
        async def ainvoke(self, value, **kwargs):
            if failure:
                raise RuntimeError('Native failure: ' + secret)
            return SimpleNamespace(output='Observed ' + secret,
                                   raw_output={'nested': [secret], 'max_tokens': 123})

    session = SimpleNamespace(load=lambda *args: Adapter())
    from agentbench.observe import store
    first_writes = []
    original = store.atomic_json

    def checked_write(path, value):
        if path.name == 'result.json':
            first_writes.append(json.dumps(value))
        return original(path, value)

    monkeypatch.setattr('agentbench.runtime.agentcontainer.worker.atomic_json', checked_write)
    code = asyncio.run(execute(root, request, output, session=session))
    assert code == int(failure)
    assert first_writes and all(secret not in value for value in first_writes)
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == ('failed' if failure else 'succeeded')
    assert '[REDACTED]' in json.dumps(result)
    if not failure:
        assert result['raw_output']['max_tokens'] == 123
    for path in output.rglob('*'):
        if path.is_file():
            assert secret not in path.read_text()
    report = json.loads((output / 'result-redaction.json').read_text())
    assert report['status'] == 'applied'
    assert report['fields'] == (['error'] if failure else ['output', 'raw_output'])


def test_sdk_submission_receives_sanitized_in_memory_result(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma.runner import drive_run
    from tests.sdk_fixtures.issue_run import sdk_run
    secret = 'fixture-native-model-credential-12345'
    monkeypatch.setenv('MINIMAX_API_KEY', secret)
    output = tmp_path / 'evaluation'
    output.mkdir()

    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'succeeded', 'output': 'Observed ' + secret,
                'raw_output': {'nested': secret}}

    with sdk_run(tmp_path / 'repo', ['Read the fixture']) as (run, provider):
        submitted = []
        original = run.submit
        def submit(**kwargs):
            submitted.append(kwargs)
            return original(**kwargs)
        monkeypatch.setattr(run, 'submit', submit)
        asyncio.run(drive_run(run, invoke, output, provider=provider))
        assert len(submitted) == 1
        assert secret not in json.dumps(submitted)
        assert submitted[0]['output'] == 'Observed [REDACTED]'
