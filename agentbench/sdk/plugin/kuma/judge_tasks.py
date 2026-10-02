"""Durable host Judge tasks using KUMA's provider and original committed evidence."""
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from agentbench.observe.timing import timing_session, span
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.judgment import DeferredJudgment
from .diagnostics import artifact_path, read_diagnostic, collect_artifacts
from .configuration import api_key, request_options

TASK = 'judge-task.json'
CONTEXT = 'evaluation/judge/context.json'


def load_context(directory):
    path = artifact_path(directory, CONTEXT)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Judge context exceeds the persisted evidence limit')
    from .judge_bundle import restore_context
    return restore_context(json.loads(path.read_text(encoding='utf-8')))


def digest(directory, relative):
    value = hashlib.sha256()
    with artifact_path(directory, relative).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def validate_execution(directory, case, *, task=None):
    """Require cleanup, trace acceptance and unchanged, correlated submissions."""
    host = read_diagnostic(directory, 'run.json')
    summary = read_diagnostic(directory, 'evaluation/manifest.json')
    if (host.get('cleanup_status') != 'succeeded'
            or host.get('host_trace_validation') != 'succeeded'
            or host.get('case_id') != case.case_id
            or host.get('run_id') != Path(directory).name
            or summary.get('case_id') != case.case_id):
        raise ValueError('Judge requires original cleanup and host trace acceptance')
    if any(summary.get(key) != expected for key, expected in (
            ('otel', 'complete'), ('submission', 'committed'), ('evidence', 'captured'))):
        raise ValueError('Judge requires committed, captured evidence')
    if summary.get('execution') not in ('succeeded', 'failed'):
        raise ValueError('Agent execution has not ended')
    context = load_context(directory)
    from kuma import to_json
    if (context.case.case_id != case.case_id
            or to_json(context.case) != read_diagnostic(directory, 'evaluation/case.json')
            or case_content_sha256(to_json(context.case)) != case.content_sha256
            or context.history[0].submission.run_id != summary.get('run_id')):
        raise ValueError('Judge context does not match the prepared Case and Run')
    if (len(context.history) != len(summary['steps'])
            or len(context.history) != len(context.case.inputs)):
        raise ValueError('Judge history is incomplete')
    relatives = [CONTEXT, 'evaluation/case.json', 'evaluation/process.json']
    for step, item in zip(summary['steps'], context.history):
        prefix = 'evaluation/' + step['directory']
        submission = read_diagnostic(directory, prefix + '/submission.json')
        result = read_diagnostic(directory, prefix + '/result.json')
        request = read_diagnostic(directory, prefix + '/request.json')
        input_data = read_diagnostic(directory, prefix + '/input.json')
        submitted_status = {'succeeded': 'completed', 'failed': 'failed', 'timeout': 'timeout',
                            'cancelled': 'aborted', 'aborted': 'aborted'}.get(result.get('status'))
        if (not step.get('committed') or step['input_id'] != item.test_input.input_id
                or submission != to_json(item.submission) or input_data != to_json(item.test_input)
                or submitted_status is None or submission.get('status') != submitted_status
                or (result.get('status') != 'succeeded' and submission.get('error') != result.get('error'))
                or result.get('output') != submission.get('output')
                or request.get('session_id') != summary['run_id']
                or request.get('run_id') != result.get('run_id')
                or request.get('agent_id') != host.get('agent_id')
                or result.get('agent_id') != host.get('agent_id')
                or read_diagnostic(directory, prefix + '/otel-status.json').get('status') != 'complete'):
            raise ValueError('Judge input/output/submission identity mismatch')
        relatives.extend(prefix + '/' + name + '.json' for name in
                         ('input', 'request', 'result', 'submission', 'otel-status', 'evidence'))
    hashes = {relative: digest(directory, relative) for relative in relatives}
    if task is not None and (task.get('evidence_sha256') != hashes
            or task.get('case_id') != case.case_id or task.get('run_id') != summary['run_id']):
        raise ValueError('Queued Judge evidence was modified')
    return host, summary, context, hashes


def prepare_task(directory, case, *, environ):
    directory = Path(directory)
    host, summary, _, hashes = validate_execution(directory, case)
    Artifacts(directory, environ=environ).save(TASK, {
        'schema': 'abb.judge-task.v1', 'state': 'queued', 'queued_at': time.time(),
        'run_id': summary['run_id'], 'case_id': case.case_id,
        'attempt_id': host.get('attempt_id'), 'evidence_sha256': hashes})
    return DeferredJudgment(directory)


class ControlledClient:
    """Stop between SDK HTTP calls; retain accepted operation state on cancellation."""
    def __init__(self, client, control, accepted=None):
        self.client, self.control, self.accepted = client, control, accepted

    def __getattr__(self, name):
        return getattr(self.client, name)

    def json(self, *args, **kwargs):
        self.control.check()
        result = self.client.json(*args, **kwargs)
        self.control.check()
        return result

    def multipart(self, *args, **kwargs):
        self.control.check()
        result = self.client.multipart(*args, **kwargs)
        if self.accepted is not None and isinstance(result.get('operation_id'), str):
            self.accepted()
        self.control.check()
        return result


def judge_task(runner, registration, case, ticket, *, on_progress=None):
    from agentbench.harness.session.locking import SuiteLock
    lock = SuiteLock(ticket.directory / 'judge-state')
    lock.acquire()
    try:
        return _judge_task(runner, registration, case, ticket, on_progress=on_progress)
    finally:
        lock.close()


def _judge_task(runner, registration, case, ticket, *, on_progress=None):
    """Submit/resume one stable Run from disk, without another Agent execution."""
    from agentbench.harness.progress import emit_progress
    from kuma.providers import OfficialJudgeProvider, normalize_report
    from kuma.transport.backend import BackendClient
    from kuma import list_requests, to_json
    from .benchmark import read_result

    directory = ticket.directory
    task = read_diagnostic(directory, TASK)
    if task.get('schema') != 'abb.judge-task.v1':
        raise ValueError('Missing durable Judge task')
    host, summary, context, _ = validate_execution(directory, case, task=task)
    if host.get('agent_id') != registration.agent_id or task.get('attempt_id') != host.get('attempt_id'):
        raise ValueError('Judge task belongs to another Attempt')
    files = Artifacts(directory, environ=runner.environ)
    if summary.get('judge') == 'received':
        # Reconcile saved reports (including the old failed-task bug) offline.
        # Never consult transport or create a replacement operation for a report.
        benchmark = read_result(directory, registration.agent_id, provider_mode=runner.provider_mode)
        files.save(TASK, {**task, 'state': 'completed', 'finished_at': task.get('finished_at') or time.time()})
        emit_progress(on_progress, stage='judge', status='succeeded', detail='Judge report received',
                      artifact_directory=str(directory),
                      **runner._identity(registration, phase='judge', case_index=case.case_index,
                          case_id=case.case_id, artifact_run_id=directory.name, sdk_run_id=summary['run_id']))
        return benchmark
    state_root = directory / 'judge-state'
    state_root.mkdir(exist_ok=True)
    requests = list_requests(state_root)
    matching = [r for r in requests if r.run_id == summary['run_id'] and r.request_type == 'judgment']
    if not matching and (task['state'] == 'judging' or task.get('request')):
        raise ValueError('Original Judge ledger is missing; replacement submission is disabled')
    if any(r.status == 'failed' for r in matching):
        raise ValueError('Original Judge operation is terminally failed; automatic replacement is disabled')
    if task['state'] == 'completed':
        return read_result(directory, registration.agent_id, provider_mode=runner.provider_mode)
    backend = read_diagnostic(directory, 'evaluation/process.json').get('sdk_base_url')
    if not isinstance(backend, str) or not backend:
        raise ValueError('Original KUMA Backend identity is missing')
    credential, _ = api_key(runner.environ)
    owner = hashlib.sha256(credential.encode('utf-8')).hexdigest()
    if task.get('credential_sha256') not in (None, owner):
        raise ValueError('Original Judge credential changed; replacement submission is disabled')
    # Seal credential ownership before the SDK can create any remote operation.
    # The SDK treats another credential as another request namespace.
    task = {**task, 'credential_sha256': owner}
    files.save(TASK, task)
    options = request_options(runner.sdk_request_options)
    wait_timeout = options.pop('operation_wait_timeout', 600.0)
    client = ControlledClient(BackendClient(api_key=credential, base_url=backend, **options), runner.control)
    provider = OfficialJudgeProvider(client, state_root=state_root, operation_wait_timeout=wait_timeout)
    identity = runner._identity(registration, phase='judge', case_index=case.case_index, case_id=case.case_id,
                                artifact_run_id=directory.name, sdk_run_id=summary['run_id'])
    with timing_session(directory / f'timing-judge-{uuid4().hex}.jsonl', source='host',
                        name='Host Judge', identity=identity):
        try:
            runner.control.check()
            if task['state'] == 'queued':
                from agentbench.observe.store import TraceStore
                start, end = task['queued_at'] * 1000, time.time() * 1000
                TraceStore(directory / 'timing-judge-queue.jsonl', summary['run_id'],
                           source='timing', context=identity).record('operation',
                    id='judge-queue-' + summary['run_id'], parent_id=None, name='Wait in Judge queue',
                    kind='wait', start_ms=start, end_ms=end, duration_ms=max(0, end - start),
                    clock_id='host-wall', source='host', status='succeeded', attributes={'clock': 'wall'})
            files.save(TASK, {**task, 'state': 'submitting', 'started_at': time.time()})
            emit_progress(on_progress, stage='judge', status='started', detail='Submitting evidence / waiting for Judge',
                          artifact_directory=str(directory), **identity)
            def accepted():
                files.save(TASK, {**task, 'state': 'judging', 'accepted_at': time.time()})
                emit_progress(on_progress, stage='judge_wait', status='started', detail='Judge request accepted; waiting for report',
                              artifact_directory=str(directory), **identity)
            client.accepted = accepted
            if any(r.operation_id for r in matching):
                accepted()
            with span('Submit Judge evidence / wait for report', kind='judge'):
                report = normalize_report(provider.judge(context), run_id=summary['run_id'])
            report = to_json(report)
            if report.get('extensions', {}).get('case_id') != case.case_id:
                raise ValueError('Judge report belongs to another Case')
            files.save('evaluation/judge/report.json', report)
            files.save('evaluation/manifest.json', {**summary, 'phase': 'finished', 'judge': 'received'})
            files.save(TASK, {**task, 'state': 'completed', 'finished_at': time.time()})
            emit_progress(on_progress, stage='judge', status='succeeded', detail='Judge report received',
                          artifact_directory=str(directory), **identity)
            return read_result(directory, registration.agent_id, provider_mode=runner.provider_mode)
        except BaseException as exc:
            # A damaged ledger must not obscure the primary failure or permit a
            # replacement paid operation when its original identity is unknown.
            ledger_readable = True
            try:
                latest = [r for r in list_requests(state_root)
                          if r.run_id == summary['run_id'] and r.request_type == 'judgment']
            except Exception:
                latest, ledger_readable = [], False
            request = max(latest, key=lambda r: r.updated_at or 0).to_dict() if latest else None
            current = read_diagnostic(directory, 'evaluation/manifest.json') or summary
            if current.get('judge') != 'received':
                files.save('evaluation/manifest.json', {**current, 'phase': 'judge', 'judge': 'failed',
                    'request': request, 'error': {'type': type(exc).__name__, 'message': str(exc),
                    'code': getattr(exc, 'code', None), 'retryable': getattr(exc, 'retryable', None)}})
            from agentbench.runtime.contracts.execution import RunCancelled
            resumable_request = (request.get('status') in {'prepared', 'queued', 'running', 'succeeded'}
                if request is not None else isinstance(exc, (RunCancelled, KeyboardInterrupt))
                or getattr(exc, 'retryable', False) is True)
            recoverable = (ledger_readable and current.get('judge') != 'received'
                           and resumable_request)
            received = current.get('judge') == 'received'
            files.save(TASK, {**task, 'state': 'completed' if received else 'interrupted' if recoverable else 'failed',
                             'request': request, 'finished_at': time.time()})
            exc.artifacts = collect_artifacts(directory,
                {**host, **({'validation': 'failed'} if received else {})}, environ=runner.environ)
            exc.artifacts['recovery'] = {
                'action': 'resume_request' if recoverable else 'blocked', 'automatic': recoverable,
                'allow_replay': False, 'reason': ('Resume the durable host Judge task without Agent replay'
                    if recoverable else 'Judge report received; result validation requires attention. Do not resubmit Judge'
                    if received else 'Judge task failed; inspect the original error before any new submission')}
            raise
