"""Vendor-neutral, versioned Judge requests over immutable ABB evidence.

Transport belongs to the selected adapter. An adapter may call an SDK or HTTP
service; core ABB never imports its optional dependencies during execution.
"""
import hashlib
import importlib
import json
from pathlib import Path
from typing import Protocol, Mapping

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.integration.cases import case_bytes, digest
from agentbench.harness.session.codec import RecoveredReport


class Judge(Protocol):
    def judge(self, request: Mapping[str, object], *, directory: Path,
              environ: Mapping[str, str]) -> Mapping[str, object]: ...


def resolve_judge(reference):
    """Explicit trusted plugin reference, never taken from a case or trace."""
    if reference == 'local':
        reference = 'agentbench.sdk.plugin.local.provider:judge'
    if reference == 'kuma':
        reference = 'agentbench.sdk.plugin.kuma.native_judge:judge'
    module, sep, name = reference.partition(':')
    if not sep or not name.isidentifier() or not all(p.isidentifier() for p in module.split('.')):
        raise ValueError('Judge must be a trusted module:object reference, local or kuma')
    judge = getattr(importlib.import_module(module), name)
    if not callable(getattr(judge, 'judge', None)):
        raise ValueError('Judge object must implement judge(request, directory=..., environ=...)')
    return judge


def build_request(directory, registration, document):
    root = Path(directory)
    from agentbench.observe.artifact_paths import artifact_file
    read = lambda name: json.loads(artifact_file(root, name).read_bytes())
    manifest = read('manifest.json')
    files, steps = {}, []
    for index, step in enumerate(manifest['steps'], 1):
        prefix = f'steps/{index:04d}'
        if step['directory'] not in (f'steps/{index:04d}', f'inputs/{index:04d}'):
            raise ValueError('Unexpected evidence step path')
        if step['directory'].startswith('inputs/'):
            prefix = 'evaluation/' + step['directory']
        # Retain payloads and file evidence referenced by spans as well as indexes.
        # These are execution-owned output files, never the Agent unit or GT.
        for path in sorted((root / prefix).rglob('*')):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Evidence attachment escapes execution directory')
            if path.is_file():
                files[relative] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'size_bytes': path.stat().st_size}
        steps.append({'input': read(prefix + '/input.json'),
                      'result': read(prefix + '/result.json'), 'evidence_prefix': prefix})
    body = {'schema': 'abb.judge.request.v1', 'agent_id': registration.agent_id,
            'run_id': manifest['run_id'], 'case': document['case'],
            'case_sha256': digest(case_bytes(document['case'])),
            'workspace': document.get('workspace'), 'steps': steps, 'attachments': files,
            'evidence_status': manifest['evidence'],
            'unexecuted_input_ids': [item['input_id'] for item in document['case']['inputs'][len(steps):]]}
    body['request_id'] = digest(case_bytes(body))
    return body


def validate_evidence(request, directory):
    body = {k: v for k, v in request.items() if k != 'request_id'}
    if request.get('schema') != 'abb.judge.request.v1' or digest(case_bytes(body)) != request.get('request_id'):
        raise ValueError('Judge request identity changed')
    root = Path(directory).resolve()
    for relative, metadata in request['attachments'].items():
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unsafe Judge attachment')
        from agentbench.observe.artifact_paths import artifact_file
        content = artifact_file(root, relative).read_bytes()
        if len(content) != metadata['size_bytes'] or digest(content) != metadata['sha256']:
            raise ValueError('Judge evidence changed')


def execute_judge(judge, request, *, directory, environ):
    from agentbench.harness.session.locking import SuiteLock
    lock = SuiteLock(Path(directory) / 'judge-protocol-lock')
    lock.acquire()
    try:
        from agentbench.observe.legacy_archive import restore_archive
        from agentbench.observe.legacy_archive import archive_manifest
        if archive_manifest(directory):
            restore_archive(directory)
        return _execute_judge(judge, request, directory=directory, environ=environ)
    finally:
        lock.close()


def validate_response(response, request):
    """Shared envelope validation for provider and externally submitted reports."""
    if (not isinstance(response, dict) or response.get('schema') != 'abb.judge.result.v1'
            or response.get('request_id') != request['request_id']
            or response.get('status') not in ('pass', 'issue', 'inconclusive')
            or not isinstance(response.get('issues'), list)
            or not isinstance(response.get('evidence_gaps'), list)):
        raise ValueError('Judge returned an invalid or mismatched response')


def _execute_judge(judge, request, *, directory, environ):
    validate_evidence(request, directory)
    files = Artifacts(directory, environ=environ)
    identity = request['request_id']
    delivery_path = Path(directory) / 'judge/delivery.json'
    from agentbench.observe.artifact_paths import artifact_file
    try:
        prior = json.loads(artifact_file(directory, 'judge/delivery.json').read_bytes())
    except FileNotFoundError:
        prior = None
    if prior is not None and prior.get('request_id') != request['request_id']:
        raise ValueError('Existing Judge task belongs to a different request')
    if prior is not None and prior.get('status') != 'received':
        raise ValueError('Previous Judge submission requires reconciliation; automatic resubmission disabled')
    files.save('judge/delivery.json', {'status': 'submitting', 'request_id': request['request_id']})
    try:
        response = (json.loads(artifact_file(directory, 'judge/report.json').read_bytes())
                    if prior is not None else judge.judge(request, directory=Path(directory), environ=environ))
        if request.get('request_id') != identity:
            raise ValueError('Judge changed its request')
        validate_evidence(request, directory)
        validate_response(response, request)
        files.save('judge/report.json', response)
        files.save('judge/delivery.json', {'status': 'received', 'request_id': request['request_id']})
        safe = json.loads(artifact_file(directory, 'judge/report.json').read_bytes())
        return RecoveredReport(safe)
    except Exception as exc:
        files.save('judge/delivery.json', {'status': 'failed', 'request_id': request['request_id'],
                                                      'error_type': type(exc).__name__})
        exc.artifacts = {'directory': str(directory), 'phase': 'judge',
                         'judge_delivery_status': 'failed', 'evidence_status': 'captured',
                         'completion': {'execution': 'succeeded' if all(
                             s['result']['status'] == 'succeeded' for s in request['steps']) else 'failed',
                                        'evidence': 'captured'}}
        raise
