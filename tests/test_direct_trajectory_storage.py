"""Final paths are usable before completion and require no archive transition."""
import hashlib
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
