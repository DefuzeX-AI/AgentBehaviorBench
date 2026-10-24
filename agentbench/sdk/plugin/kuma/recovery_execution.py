"""Recover a Judge request for its original Case Attempt, without Agent replay."""
from agentbench.observe.timing import timing_session, span
from pathlib import Path
from uuid import uuid4

from agentbench.harness.progress import emit_progress
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.case_identity import case_content_sha256

from .error_artifacts import exception_record
from .case_files import artifact_digest
from .diagnostics import collect_artifacts, read_diagnostic
from .request_recovery import inspect_requests, recover_request


def recover_case(runner, registration, case, *, previous_result, validator, on_progress=None):
    """Poll the exact previous request; publish only after full host validation.

    Args:
        previous_result: Failed CaseResult with the original Attempt artifacts.
        validator: Normal host result reader supporting a candidate recovered report.
    Returns:
        BenchmarkResult for the same SDK Run and original Input evidence.
    Side effects:
        Public SDK recovery GETs may update its ledger. Recovery snapshots and an
        accepted report are saved in the original Attempt, never a new execution.
    """
    runner.control.check()
    runner.validate_sdk(registration)
    artifacts = previous_result.artifacts or {}
    if (previous_result.agent_id != registration.agent_id or previous_result.case_index != case.case_index
            or previous_result.case_id != case.case_id):
        raise ValueError('Recovery selection does not match the original Case')
    if (not case.artifact_path or case.artifact_path.is_symlink()
            or artifact_digest(case.artifact_path, runner.control) != case.artifact_sha256):
        raise ValueError('Prepared Case changed before request recovery')
    original = artifacts.get('directory')
    if not isinstance(original, str) or not Path(original).is_absolute():
        raise ValueError('Recovery requires the original artifact directory')
    directory = Path(original)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Recovery artifact directory is missing or linked')
    from agentbench.observe.legacy_archive import restore_archive
    from agentbench.observe.legacy_archive import archive_manifest
    if archive_manifest(directory):
        restore_archive(directory)
    timing_id = uuid4().hex
    timing_identity = runner._identity(registration, phase='recover', case_index=case.case_index, case_id=case.case_id)
    with timing_session(directory / f'timing-recovery-{timing_id}.jsonl', source='host',
                        name='Judge recovery', identity=timing_identity):
        host = read_diagnostic(directory, 'run.json')
        summary = read_diagnostic(directory, 'manifest.json')
        current_case = read_diagnostic(directory, 'case.json')
        if (host.get('agent_id') != registration.agent_id or host.get('run_id') != directory.name
                or host.get('case_id') != case.case_id or summary.get('case_id') != case.case_id
                or current_case.get('case_id') != case.case_id
                or case_content_sha256(current_case) != case.content_sha256):
            raise ValueError('Recovery artifacts do not match the selected original Case')
        if host.get('attempt_id') not in (None, previous_result.attempt_id):
            raise ValueError('Recovery artifacts belong to another Attempt')
        received = read_diagnostic(directory, 'judge/report.json')
        if received and summary.get('judge') == 'received':
            # The SDK and host already finished; a coordinator crash may have lost
            # only case_completed. Reconcile the saved result without any SDK call.
            result = validator(directory, registration.agent_id, recovered_report=received)
            files = Artifacts(directory, environ=runner.environ)
            recovery_id = uuid4().hex
            files.save(f'recovery/{recovery_id}/before.json', {'host': host, 'manifest': summary})
            files.save('run.json', {**host, 'status': 'succeeded', 'validation': 'succeeded',
                                   'recovery_id': recovery_id})
            files.save(f'recovery/{recovery_id}/acceptance.json', {
                'host_accepted': True, 'run_id': result.run_id, 'source': 'existing_report'})
            return result
        diagnostics = collect_artifacts(directory, host, environ=runner.environ)
        recovery = diagnostics['recovery']
        if recovery['action'] != 'resume_request':
            error = RuntimeError(recovery['reason'])
            error.artifacts = diagnostics
            raise error
        client_id = recovery['client_request_id']
        repository = directory / 'sdk-repo'
        request = inspect_requests(repository, client_id)
        _check_request(request, summary, client_id)
        # Terminally failed requests are not reopened even when a stale manifest
        # still recorded them as pending before the earlier process exited.
        if request.get('status') == 'failed':
            raise _failed_request(directory, runner, host, summary, request)
        process = read_diagnostic(directory, 'process.json')
        base_url = process.get('sdk_base_url')
        if not isinstance(base_url, str) or not base_url:
            raise ValueError('Original SDK Backend identity was not recorded; recovery is unavailable')
        files = Artifacts(directory, environ=runner.environ)
        recovery_id = uuid4().hex
        prefix = f'recovery/{recovery_id}'
        files.save(f'{prefix}/before.json', {'host': host, 'manifest': summary, 'request': request})
        identity = runner._identity(registration, phase='judge', case_index=case.case_index, case_id=case.case_id)
        emit_progress(on_progress, stage='benchmark_execution', status='started',
                      detail='Resuming the original Judge request', artifact_directory=str(directory),
                      artifact_run_id=directory.name, sdk_run_id=summary['run_id'], **identity)
        validating = False
        try:
            with span('Resume Judge request', kind='sdk_wait'):
                recovered = recover_request(repository, client_id, environ=runner.environ, base_url=base_url,
                                            expected_run_id=summary['run_id'], expected_case_id=case.case_id,
                                            options=runner.sdk_request_options)
            runner.control.check()
            _check_request(recovered['request'], summary, client_id)
            files.save(f'{prefix}/request.json', recovered['request'])
            if recovered['request'].get('status') == 'failed':
                raise _failed_request(directory, runner, host, summary, recovered['request'])
            report = recovered.get('report')
            if recovered['request'].get('status') != 'succeeded' or not isinstance(report, dict):
                raise RuntimeError('Original Judge request has not yielded a valid report')
            files.save(f'{prefix}/report.json', report)
            validating = True
            result = validator(directory, registration.agent_id, recovered_report=report)
            # All checks passed before changing the visible report or terminal state.
            files.save('judge/report.json', report)
            files.save('manifest.json', {**summary, 'phase': 'finished', 'judge': 'received',
                                                  'request': recovered['request'], 'recovery_id': recovery_id})
            files.save('run.json', {**host, 'status': 'succeeded', 'validation': 'succeeded',
                                   'recovery_id': recovery_id})
            files.save(f'{prefix}/acceptance.json', {'host_accepted': True, 'run_id': result.run_id})
            return result
        except Exception as exc:
            # Never relabel a failed recovery as an accepted benchmark. Preserve the
            # public updated request state for the next coordinator decision.
            try:
                latest = inspect_requests(repository, client_id)
                _check_request(latest, summary, client_id)
                current_error = exception_record(exc, phase='judge')
                files.save('manifest.json', {**summary, 'request': latest, 'error': current_error})
            except Exception:
                pass
            recovery_error = exception_record(exc, phase='judge')
            files.save(f'{prefix}/error.json', {**recovery_error,
                'error_type': recovery_error['type'], 'error_message': recovery_error['message']})
            exc.artifacts = collect_artifacts(directory, host, environ=runner.environ)
            if validating:
                exc.artifacts['recovery'] = {'action': 'blocked', 'automatic': False,
                                            'reason': 'Recovered report did not complete host validation/publication'}
            raise


def _check_request(request, summary, client_id):
    if any(request.get(key) != expected for key, expected in (
        ('client_request_id', client_id), ('request_type', 'judgment'),
        ('run_id', summary['run_id']), ('case_id', summary['case_id']))):
        raise ValueError('Recovery request does not match the original Judge identity')


def _failed_request(directory, runner, host, summary, request):
    Artifacts(directory, environ=runner.environ).save('manifest.json', {**summary, 'request': request})
    error = RuntimeError('The original Judge request is terminally failed and cannot be resumed')
    error.artifacts = collect_artifacts(directory, host, environ=runner.environ)
    return error
