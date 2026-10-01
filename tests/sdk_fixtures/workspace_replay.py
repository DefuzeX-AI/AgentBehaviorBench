"""Offline real-container replay acceptance through the production SDK worker."""
import asyncio
import json
from pathlib import Path
from tests.sdk_fixtures.agent_owned_session import write_agent, execute_case


async def main():
    root = Path('/tmp/replay-agent')
    write_agent(root)
    source = next((root / 'agent').glob('sqlite_agent_*.py'))
    text = source.read_text()
    text = text.replace('        question = state["question"]',
        '        question = state["question"]\n'
        '        (self.directory / "note.txt").write_text(question, encoding="utf-8")')
    source.write_text(text)
    output = Path('/artifacts/evaluation')
    result = await execute_case(root, Path('/tmp/replay-work'), output,
        ['remember blue', 'remember green', 'recall'], ['blue', 'green', 'green'], allow_local=False)
    assert result['exit_code'] == 0
    archive = Path('/run/abb-replay')
    manifest = json.loads((archive / 'manifest.json').read_text())
    assert manifest['status'] == 'complete', manifest
    assert manifest['capture_mode'] == 'notifications_with_reconciliation'
    events = [json.loads(line) for line in (archive / 'events.jsonl').read_text().splitlines()]
    versions = [change['after']['blob'] for event in events for change in event['changes']
                if change['path'] == 'note.txt' and change['after']]
    contents = [(archive / 'blobs' / version).read_text() for version in versions]
    assert contents == ['remember blue', 'remember green', 'recall'], contents
    assert len([e for e in events if e['reason'] == 'input_end']) == 3
    assert any(change['path'] == 'agent-closed.json' for event in events for change in event['changes'])
    assert all(not change['path'].startswith(('.kuma/', 'replay/')) for event in events for change in event['changes'])
    for path in output.glob('inputs/*/submission.json'):
        submission = path.read_text()
        assert 'abb.workspace-replay' not in submission
        assert '/run/abb-replay' not in submission
        assert not any(blob in submission for blob in versions)
    Path('/artifacts/acceptance.json').write_text(json.dumps({
        'status': 'passed', 'real_container': True, 'real_sdk': result['sdk_version'],
        'remote_services_called': False, 'file_versions': contents,
        'capture_mode': manifest['capture_mode'], 'judge': result['judge_calls'],
        'replay_in_submissions': False}, indent=2))
    print('PASS: three file versions, round checkpoints, final cleanup, local-only storage, real SDK Judge')


if __name__ == '__main__':
    asyncio.run(main())
