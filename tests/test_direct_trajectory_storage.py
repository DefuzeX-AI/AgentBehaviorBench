"""Final paths are usable before completion and require no archive transition."""
import hashlib
import errno
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.observe.artifact_paths import artifact_file
from agentbench.observe.payloads import publish_payload
from agentbench.observe.view_api import RunViewAPI
from agentbench.sdk.common.artifacts import Artifacts


def test_running_failed_and_resumed_execution_use_same_plain_files(tmp_path, monkeypatch):
    from agentbench.observe import legacy_archive
    monkeypatch.setattr(legacy_archive, 'restore_archive',
                        lambda *a: pytest.fail('New execution must never restore an archive'))
    root = tmp_path / 'trajectory/run'
    files = Artifacts(root)
    files.save('manifest.json', {'phase': 'execution', 'steps': [{'directory': 'steps/0001'}]})
    files.save('steps/0001/result.json', {'output': 'committed'})
    original = (root / 'steps/0001/result.json').read_bytes()
    api = RunViewAPI(root)
    assert api.outputs() == ['steps/0001']
    assert api.read('evaluation/inputs/0001/result.json')['output'] == 'committed'
    files.save('manifest.json', {'phase': 'judge', 'judge': 'failed'})
    files.save('judge/report.json', {'status': 'pass'})
    assert api.evaluation()['judge']['status'] == 'pass'
    assert (root / 'steps/0001/result.json').read_bytes() == original
    assert not (root / 'evaluation').exists()
    assert json.loads((root / 'manifest.json').read_bytes()).get('schema') != 'abb.trajectory.v1'


def test_payloads_in_two_steps_share_one_immutable_blob_at_write_time(tmp_path):
    raw = b'{"text": "same payload"}'
    targets = []
    for index in (1, 2):
        step = tmp_path / 'steps' / f'{index:04d}'
        target = step / 'otel-payloads/value.json'
        target.parent.mkdir(parents=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(raw)
        publish_payload(temporary, target, step)
        targets.append(target)
        assert target.read_bytes() == raw
    blob, = (tmp_path / 'blobs').iterdir()
    assert blob.name == hashlib.sha256(raw).hexdigest()
    assert os.path.samefile(targets[0], blob) and os.path.samefile(targets[1], blob)


def test_payload_publication_rejects_corrupt_existing_blob(tmp_path):
    raw = b'payload'
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary = step / 'tmp'
    temporary.write_bytes(raw)
    blob = tmp_path / 'blobs' / hashlib.sha256(raw).hexdigest()
    blob.parent.mkdir()
    blob.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='digest mismatch'):
        publish_payload(temporary, step / 'payload.json', step)
    assert temporary.read_bytes() == raw


def test_new_payload_does_not_reopen_just_published_blob(tmp_path, monkeypatch):
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary, target = step / 'incoming', step / 'payload.json'
    temporary.write_bytes(b'complete payload')
    link = os.link
    calls = []

    def transient_link(source, destination):
        calls.append((source, destination))
        if len(calls) > 1:
            raise FileNotFoundError(errno.ENOENT, 'new blob not visible yet')
        return link(source, destination)

    monkeypatch.setattr(os, 'link', transient_link)
    publish_payload(temporary, target, step)
    assert target.read_bytes() == b'complete payload'
    blob, = (tmp_path / 'blobs').iterdir()
    assert os.path.samefile(blob, target)
    assert len(calls) == 1


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('error', [errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EACCES])
def test_optional_payload_link_failure_publishes_complete_file(tmp_path, monkeypatch, existing, error):
    _check_payload_link_failure(tmp_path, monkeypatch, existing, error)


def test_existing_payload_disappears_before_link_without_losing_copy(tmp_path, monkeypatch):
    _check_payload_link_failure(tmp_path, monkeypatch, True, errno.ENOENT)


def _check_payload_link_failure(tmp_path, monkeypatch, existing, error):
    raw = b'complete new payload'
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary, target = step / 'incoming', step / 'payload.json'
    temporary.write_bytes(raw)
    target.write_bytes(b'previous complete payload')
    blob = tmp_path / 'blobs' / hashlib.sha256(raw).hexdigest()
    blob.parent.mkdir()
    if existing:
        blob.write_bytes(raw)
    link = os.link

    def failed_link(source, destination):
        if existing and Path(destination) == blob:
            return link(source, destination)
        assert temporary.read_bytes() == raw
        assert target.read_bytes() == b'previous complete payload'
        if error == errno.ENOENT:
            blob.unlink()
        raise OSError(error, 'injected optional-link failure')

    monkeypatch.setattr(os, 'link', failed_link)
    publish_payload(temporary, target, step)
    assert target.read_bytes() == raw
    assert not temporary.exists()
    assert sorted(p.name for p in step.iterdir()) == ['payload.json']
    if blob.exists():
        assert hashlib.sha256(blob.read_bytes()).hexdigest() == blob.name


def test_unexpected_payload_link_failure_keeps_original_and_target(tmp_path, monkeypatch):
    raw = b'complete payload'
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary, target = step / 'incoming', step / 'payload.json'
    temporary.write_bytes(raw)
    target.write_bytes(b'old payload')
    blob = tmp_path / 'blobs' / hashlib.sha256(raw).hexdigest()
    blob.parent.mkdir()
    blob.write_bytes(raw)
    link = os.link

    def failed_link(source, destination):
        if Path(destination) == blob:
            return link(source, destination)
        raise OSError(errno.EIO, 'injected I/O failure')

    monkeypatch.setattr(os, 'link', failed_link)
    with pytest.raises(OSError) as exc:
        publish_payload(temporary, target, step)
    assert exc.value.errno == errno.EIO
    assert temporary.read_bytes() == raw
    assert target.read_bytes() == b'old payload'


@pytest.mark.parametrize('existing', [False, True])
def test_payload_publish_failure_does_not_replace_previous_target(tmp_path, monkeypatch, existing):
    raw = b'complete payload'
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary, target = step / 'incoming', step / 'payload.json'
    temporary.write_bytes(raw)
    target.write_bytes(b'old payload')
    blob = tmp_path / 'blobs' / hashlib.sha256(raw).hexdigest()
    blob.parent.mkdir()
    if existing:
        blob.write_bytes(raw)
    replace = Path.replace

    def failed_replace(source, destination):
        if destination == target:
            assert temporary.read_bytes() == raw
            assert target.read_bytes() == b'old payload'
            raise OSError(errno.EIO, 'injected atomic-publication failure')
        return replace(source, destination)

    monkeypatch.setattr(Path, 'replace', failed_replace)
    with pytest.raises(OSError, match='atomic-publication'):
        publish_payload(temporary, target, step)
    assert temporary.read_bytes() == raw
    assert target.read_bytes() == b'old payload'
    assert blob.read_bytes() == raw
    assert sorted(p.name for p in step.iterdir()) == ['incoming', 'payload.json']


def test_payload_publication_rejects_linked_blob_without_losing_copy(tmp_path):
    raw = b'complete payload'
    step = tmp_path / 'steps/0001'
    step.mkdir(parents=True)
    temporary, target = step / 'incoming', step / 'payload.json'
    temporary.write_bytes(raw)
    target.write_bytes(b'old payload')
    blob = tmp_path / 'blobs' / hashlib.sha256(raw).hexdigest()
    blob.parent.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(raw)
    blob.symlink_to(outside)
    with pytest.raises(ValueError, match='Linked'):
        publish_payload(temporary, target, step)
    assert temporary.read_bytes() == raw
    assert target.read_bytes() == b'old payload'


def test_judge_context_references_committed_files_and_detects_changes(tmp_path, monkeypatch):
    pytest.importorskip('kuma')
    from agentbench.sdk.plugin.kuma import judge_bundle
    case = {'case_id': 'original'}
    item = {'test_input': {'input_id': 'i'}, 'submission': {'output': 'answer'}}
    monkeypatch.setattr(judge_bundle, 'export_context', lambda *a, **k: {
        'schema': judge_bundle.SCHEMA, 'case': case, 'history': [item]})
    files = Artifacts(tmp_path)
    files.save('case.json', case)
    files.save('steps/0001/input.json', item['test_input'])
    files.save('steps/0001/submission.json', item['submission'])
    judge_bundle.save_context(files, None, case)
    value = json.loads((tmp_path / 'judge/context.json').read_bytes())
    assert 'answer' not in json.dumps(value)
    assert judge_bundle.read_context(tmp_path, value)['history'] == [item]
    files.save('steps/0001/submission.json', {'output': 'changed'})
    with pytest.raises(ValueError, match='modified'):
        judge_bundle.read_context(tmp_path, value)


def test_transport_cleanup_preserves_committed_artifacts(tmp_path):
    from agentbench.sdk.integration.execution import cleanup_transport
    files = Artifacts(tmp_path)
    for name in ('channel/response/copy.json', 'agent-output/copy.json',
                 'agent-request/request.json', 'steps/0001/result.json',
                 'judge/context.json', 'sdk-repo/ledger.json'):
        files.save(name, {'keep': name})
    cleanup_transport(tmp_path)
    assert not (tmp_path / 'channel').exists()
    assert not (tmp_path / 'agent-output').exists()
    assert not (tmp_path / 'agent-request').exists()
    for name in ('steps/0001/result.json', 'judge/context.json', 'sdk-repo/ledger.json'):
        assert json.loads((tmp_path / name).read_bytes()) == {'keep': name}


def test_exporter_reuses_payload_across_spans_after_redaction(tmp_path, monkeypatch):
    from agentbench.observe.otel.exporter import FileExporter
    exporter = FileExporter(tmp_path, 'invocation', 'session', ())
    monkeypatch.setattr(exporter, 'export', lambda *a, **k: None)
    first = SimpleNamespace(context=SimpleNamespace(span_id=1))
    second = SimpleNamespace(context=SimpleNamespace(span_id=2))
    exporter.payload(first, 'input', {'value': 'same'})
    exporter.payload(second, 'output', {'value': 'same'})
    assert exporter.local(first, 'abb.input_ref') == exporter.local(second, 'abb.output_ref')
    assert len(list((tmp_path / 'otel-payloads').iterdir())) == 1
