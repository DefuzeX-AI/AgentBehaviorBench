import json
import time
from pathlib import Path

import pytest

from agentbench.runtime.workspace_replay import WorkspaceRecorder
from agentbench.observe.replay import replay


def setup_recorder(tmp_path, **kwargs):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'note.txt').write_text('initial', encoding='utf-8')
    archive = tmp_path / 'run' / 'replay'
    archive.parent.mkdir()
    (archive.parent / 'run.json').write_text('{"status":"running"}')
    return workspace, archive, WorkspaceRecorder(workspace, archive, interval=0.02, **kwargs)


def test_versions_survive_workspace_deletion_and_blob_deduplication(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path)
    try:
        (workspace / 'note.txt').write_text('changed', encoding='utf-8')
        recorder.capture('input_end', input_id='input-a', force=True)
        (workspace / 'copy.txt').write_text('changed', encoding='utf-8')
        recorder.capture('input_end', force=True)
        (workspace / 'note.txt').unlink()
        recorder.capture('input_end', force=True)
        (workspace / 'copy.txt').unlink()
        workspace.rmdir()
    finally:
        recorder.finish()
    data = replay(archive.parent, {})
    changes = [change for event in data['events'] for change in event['changes']]
    assert any(c['path'] == 'note.txt' and c['after'] is None for c in changes)
    assert len(list((archive / 'blobs').iterdir())) == 2
    initial = data['baseline']['entries']['note.txt']['blob']
    assert replay(archive.parent, {'blob': initial})['text'] == 'initial'
    assert data['manifest']['status'] == 'partial'  # removed workspace cannot be fully scanned


def test_background_capture_and_boundaries_are_observed_not_tool_attributed(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path)
    try:
        (workspace / 'note.txt').write_text('background', encoding='utf-8')
        deadline = time.monotonic() + 3
        while recorder.entries['note.txt']['blob'] == json.loads((archive / 'baseline.json').read_text())['entries']['note.txt']['blob']:
            if time.monotonic() > deadline:
                pytest.fail('Background recorder did not see the write')
            time.sleep(0.02)
        recorder.capture('input_end', input_id='input-1', force=True)
    finally:
        recorder.finish()
    data = replay(archive.parent, {})
    assert data['manifest']['status'] == 'complete'
    assert any(e['reason'] == 'input_end' and e['input_id'] == 'input-1' for e in data['events'])
    assert all('tool_id' not in e for e in data['events'])


def test_limits_exclusions_redaction_and_no_self_observation(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path, secrets=['very-secret-key'], max_file_bytes=100)
    try:
        (workspace / '.kuma').mkdir()
        (workspace / '.kuma' / 'ledger.json').write_text('private ledger')
        (workspace / '.env').write_text('hidden')
        (workspace / 'large.txt').write_text('x' * 101)
        (workspace / 'token.txt').write_text('very-secret-key')
        recorder.capture('input_end', force=True)
    finally:
        recorder.finish()
    assert not any('.kuma' in path or 'replay' in path for path in recorder.entries)
    assert recorder.entries['.env']['omitted'] == 'sensitive_path'
    assert recorder.entries['large.txt']['omitted'] == 'file_size_limit'
    assert recorder.entries['token.txt']['redacted'] is True
    assert all(b'very-secret-key' not in f.read_bytes() for f in (archive / 'blobs').iterdir())
    with pytest.raises(ValueError, match='outside'):
        WorkspaceRecorder(workspace, workspace / 'replay')


def test_unreadable_file_preserves_known_state_with_warning(tmp_path, monkeypatch):
    workspace, archive, recorder = setup_recorder(tmp_path)
    try:
        monkeypatch.setattr(recorder, '_content', lambda *args: (_ for _ in ()).throw(PermissionError()))
        recorder.capture('input_end', force=True)
        assert recorder.entries['note.txt']['blob']
    finally:
        recorder.finish()
    assert replay(archive.parent, {})['warnings']


def test_api_rejects_traversal_and_reports_truncated_tail(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path)
    recorder.finish()
    with (archive / 'events.jsonl').open('a') as stream:
        stream.write('{"sequence":')
    assert replay(archive.parent, {})['warnings']
    with pytest.raises(ValueError):
        replay(archive.parent, {'blob': '../../private'})
    with pytest.raises(ValueError):
        replay(archive.parent, {'offset': '-1'})


def test_legacy_run_has_no_fabricated_files(tmp_path):
    assert replay(tmp_path, {}) == {'available': False, 'events': [], 'next': None, 'warnings': []}


def test_archive_is_immutable_and_event_storage_limits_are_explicit(tmp_path, monkeypatch):
    workspace, archive, recorder = setup_recorder(tmp_path)
    baseline = (archive / 'baseline.json').read_bytes()
    monkeypatch.setattr('agentbench.runtime.workspace_replay.MAX_METADATA_BYTES', 10)
    try:
        (workspace / 'note.txt').write_text('new version', encoding='utf-8')
        recorder.capture('input_end', force=True)
    finally:
        recorder.finish()
    assert replay(archive.parent, {})['manifest']['status'] == 'partial'
    assert replay(archive.parent, {})['warnings']
    with pytest.raises(FileExistsError):
        WorkspaceRecorder(workspace, archive)
    assert (archive / 'baseline.json').read_bytes() == baseline


def test_api_frozen_version_excludes_later_events(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path)
    try:
        recorder.capture('input_end', input_id='first')
        first_version = recorder.sequence
        recorder.capture('input_end', input_id='second')
    finally:
        recorder.finish()
    assert all(event['sequence'] <= first_version for event in replay(archive.parent, {'through': str(first_version)})['events'])


def test_symlink_is_not_followed(tmp_path):
    workspace, archive, recorder = setup_recorder(tmp_path)
    try:
        external = tmp_path / 'private.txt'
        external.write_text('outside-private')
        try:
            (workspace / 'link.txt').symlink_to(external)
        except OSError:
            pytest.skip('Host does not allow symlinks')
        recorder.capture('input_end', force=True)
        assert recorder.entries['link.txt']['omitted'] == 'link_not_followed'
        assert all(b'outside-private' not in f.read_bytes() for f in (archive / 'blobs').iterdir())
    finally:
        recorder.finish()


class OfflineBackend:
    """Controlled Backend responses; the real SDK owns request serialization/ledger."""
    base_url = 'https://offline.example/api'
    api_key = 'dfx_offline_fixture_only'
    def __init__(self, case_id):
        self.case_id = case_id
        self.posts = []
        self.polls = 0
        self.interrupt = False

    def json(self, method, path, *args, **kwargs):
        if path == '/sdk/judge/config/':
            return {'allowed_extensions': ['.json'], 'max_files': 20,
                    'max_file_bytes': 5 * 1024 * 1024, 'max_total_bytes': 8 * 1024 * 1024,
                    'manifest_schema_version': '1', 'evidence_types': ['raw_log', 'defuzex.runtime_evidence.capabilities.v1'],
                    'runtime_evidence_capabilities': ['runtime_evidence', 'agent_output', 'file_diff', 'runtime_trace']}
        if path.startswith('/sdk/v2/operations/'):
            self.polls += 1
            if self.interrupt:
                raise KeyboardInterrupt()
            return {'operation_id': 'operation-judge-offline', 'status': 'succeeded',
                    'result': {'judgment_id': 'judge-offline', 'case_id': self.case_id, 'status': 'pass',
                               'confidence': 'high', 'issues': [], 'step_results': [], 'flags': {}}}
        raise AssertionError(path)

    def multipart(self, path, fields, parts, **kwargs):
        assert path == '/sdk/v2/judge/'
        self.posts.append((fields, parts, kwargs))
        return {'operation_id': 'operation-judge-offline', 'status': 'queued', 'poll_after_ms': 100}


def test_replay_is_outside_kuma_mount_and_submission(tmp_path):
    import asyncio
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from kuma.providers import OfficialJudgeProvider
    from opentelemetry.sdk.trace import TracerProvider
    from agentbench.sdk.plugin.kuma.service import EvaluationPolicy
    from agentbench.sdk.plugin.kuma.runner import drive_run
    from agentbench.sdk.common.artifacts import Artifacts
    from tests.sdk_fixtures.issue_run import profile

    archive = tmp_path / 'attempt' / 'replay'
    archive.mkdir(parents=True)
    marker = 'ABB_LOCAL_ONLY_VERSION_MUST_NEVER_UPLOAD'
    (archive / 'events.jsonl').write_text(marker)
    repo = tmp_path / 'repo'
    profile_path = profile(repo)
    policy = EvaluationPolicy(repo / '.kuma', repository=repo, replay=archive)
    assert f'type=bind,source={archive},target=/run/abb-replay' in policy.run_arguments()
    backend = OfflineBackend('replay-case')
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    run = create_run(repo_path=repo, agent_profile_path=profile_path, allow_local=True,
        case_provider=lambda _: {'case_id': 'replay-case', 'inputs': ['remember blue']},
        judge_provider=OfficialJudgeProvider(backend), max_steps=1,
        track_files=True, upload_diff=True, trace_evidence=capture)
    async def invoke(payload, folder, shared_provider):
        files = Artifacts(folder)
        with provider.get_tracer('fixture').start_as_current_span('write note') as operation:
            operation.set_attribute('gen_ai.operation.name', 'execute_tool')
            operation.set_attribute('gen_ai.tool.name', 'write')
            (repo / 'note.txt').write_text('blue', encoding='utf-8')
        files.save('request.json', {'agent_id': 'fixture-agent', 'run_id': folder.name, 'session_id': run.run_id})
        files.save('otel-status.json', {'status': 'complete'})
        return {'schema': 'abb.result.v1', 'agent_id': 'fixture-agent', 'run_id': folder.name,
                'status': 'succeeded', 'output': 'blue'}
    try:
        summary = asyncio.run(drive_run(run, invoke, archive.parent / 'evaluation', provider=provider,
            repo_path=repo, file_evidence_required=True))
        assert summary['judge'] == 'received'
    finally:
        provider.shutdown()
    assert len(backend.posts) == 1
    fields, parts, _ = backend.posts[0]
    assert parts  # Inspect actual SDK multipart bytes, not a mock schema.
    assert all(marker.encode() not in part.data and b'/run/abb-replay' not in part.data for part in parts)
    assert marker not in repr(fields)
