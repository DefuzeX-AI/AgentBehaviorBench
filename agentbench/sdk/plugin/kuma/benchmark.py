"""Shared container Case executor for run, certify and the evaluate alias."""
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from agentbench.adapter import AdapterInvocation
from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.progress import emit_progress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult, BenchmarkStepFailure
from agentbench.runtime.contracts.execution import RunControl
from agentbench.runtime.interception import resolve_model_provider
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.contracts import PreparedCase, PreparedCaseBatch, RunnerRecoveryCapabilities
from agentbench.sdk.common.case_identity import case_content_sha256

from .service import evaluate
from .diagnostics import evaluation_failure, collect_artifacts, host_acceptance, artifact_path
from .configuration import backend_url, request_options, api_key, validate_host_judge_dependency
from .case_files import artifact_digest
from .preparation import prepare_batch


@dataclass(frozen=True)
class Report:
    status: str
    confidence: object
    issues: tuple
    evidence_gaps: tuple
    report_id: str
    run_id: str
    extensions: dict


class KumaContainerRunner:
    """Prepare immutable Case slots or execute one explicitly selected Case."""

    # Reported as the run's provider mode; a plugin reusing this runner renames it.
    provider_mode = 'official-container'
    supports_deferred_judgment = True

    def __init__(self, *, environ=None, options=None, trace_sink=None, trace_max_bytes=262144,
                 control=None, build_coordinator=None, job_context=None,
                 runtime_services=None):
        self.environ = dict(os.environ if environ is None else environ)
        options = dict(options or {})
        unknown = set(options) - {'output', 'timeout', 'max_steps', 'case_collection', 'sdk_request_options'}
        if unknown:
            raise ProviderSelectionError(f'Unsupported container evaluation options: {sorted(unknown)}')
        self.output = Path(options.get('output', 'results/observe'))
        try:
            self.sdk_request_options = request_options(options.get('sdk_request_options'))
        except ValueError as exc:
            raise ProviderSelectionError(str(exc)) from exc
        self.timeout = options.get('timeout', 2400)
        if (isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float))
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ProviderSelectionError('Container timeout must be a positive finite number')
        self.case_collection = Path(options['case_collection']) if options.get('case_collection') is not None else None
        self.max_steps = options.get('max_steps')
        if self.max_steps is not None and (type(self.max_steps) is not int or self.max_steps < 1):
            raise ProviderSelectionError('max_steps must be a positive integer')
        self.trace_sink = trace_sink
        self.trace_max_bytes = trace_max_bytes
        self.control = control or RunControl()
        self.build_coordinator = build_coordinator
        self.job_context = dict(job_context or {})
        self.runtime_services = runtime_services

    def _identity(self, registration, **fields):
        return {**self.job_context, 'agent_id': registration.agent_id, **fields}

    def _runtime_options(self, identity):
        return dict(control=self.control, build_coordinator=self.build_coordinator,
                    runtime_services=self.runtime_services, identity=identity,
                    sdk_request_options=self.sdk_request_options)

    def _artifacts_ready(self, registration, on_progress, path, identity, detail):
        emit_progress(
            on_progress, stage='case_generation' if identity['phase'] == 'generate' else 'benchmark_execution',
            status='started', detail=detail, artifact_directory=str(path), artifact_run_id=path.name,
            case_count=registration.case_count, **identity,
        )

    def validate_sdk(self, registration):
        try:
            api_key(self.environ)
            backend_url(self.environ)
            validate_host_judge_dependency()
            # Only replacement depends on a BBA-selected Agent model provider.
            if DEFAULT_ADAPTER_FACTORY.network_mode(getattr(registration, 'framework', 'langgraph')) == 'replace':
                resolve_model_provider(environ=self.environ)
        except ValueError as exc:
            raise ProviderSelectionError(str(exc)) from exc
        if not (registration.path / 'requirement.md').is_file():
            raise ProviderSelectionError('Missing Agent evaluation file: requirement.md')
        return self.provider_mode

    def _evaluate(self, registration, **options):
        """Run one generation or execution container; a subclass may reconfigure it."""
        return evaluate(registration, **options)

    def recovery_capabilities(self, registration) -> RunnerRecoveryCapabilities:
        """Combine public request recovery with an explicit Agent replay promise."""
        from agentbench.sdk.common.replay import safe_case_replay
        return RunnerRecoveryCapabilities(safe_case_replay(registration), resume_judgment=True)

    def prepare_cases(self, registration, *, on_progress=None) -> tuple[PreparedCase, ...]:
        """Legacy API: require the complete imported/generated selection."""
        return prepare_batch(self, registration, evaluator=self._evaluate,
                             on_progress=on_progress, allow_partial=False).cases

    def prepare_case_batch(self, registration, *, case_indices=None,
                           on_progress=None) -> PreparedCaseBatch:
        """Return successful Cases, failures and unattempted original slot IDs.

        ``case_indices`` selects only missing zero-based slots. Complete saved
        collection imports remain strict; other generated slots can survive a
        single generation failure. This method never retries a failed request.
        """
        return prepare_batch(self, registration, evaluator=self._evaluate,
                             case_indices=case_indices, on_progress=on_progress)

    def recover_case(self, registration, case: PreparedCase, *, previous_result,
                     on_progress=None, on_step_start=None, on_step_complete=None,
                     on_step_failure=None) -> BenchmarkResult:
        """Resume the original Judge request and validate its unchanged evidence."""
        from .recovery_execution import recover_case
        try:
            directory = (previous_result.artifacts or {}).get('directory')
            if directory and ((Path(directory) / 'judge-task.json').is_file()
                              or (Path(directory) / 'evaluation/judge/context.json').is_file()):
                from agentbench.sdk.judgment import DeferredJudgment
                from .judge_tasks import prepare_task
                from .diagnostics import read_diagnostic
                host = read_diagnostic(Path(directory), 'run.json')
                if (previous_result.agent_id != registration.agent_id
                        or previous_result.case_index != case.case_index
                        or previous_result.case_id != case.case_id
                        or host.get('attempt_id') != previous_result.attempt_id):
                    raise ValueError('Judge recovery belongs to another Case or Attempt')
                ticket = (DeferredJudgment(Path(directory)) if (Path(directory) / 'judge-task.json').is_file()
                          else prepare_task(Path(directory), case, environ=self.environ))
                return self.judge_case(registration, case, ticket,
                    on_progress=on_progress, on_step_start=on_step_start,
                    on_step_complete=on_step_complete, on_step_failure=on_step_failure)
            return recover_case(self, registration, case, previous_result=previous_result,
                                validator=read_result, on_progress=on_progress)
        except Exception as exc:
            if not getattr(exc, 'artifacts', None):
                exc.artifacts = {**(previous_result.artifacts or {}), 'recovery': {
                    'action': 'blocked', 'automatic': False, 'reason': str(exc)}}
            raise

    def execute_case(self, registration, case, **callbacks):
        return self.run_case(registration, case, _defer_judge=True, **callbacks)

    def judge_case(self, registration, case, ticket, *, on_progress=None,
                   on_step_start=None, on_step_complete=None, on_step_failure=None):
        from .judge_tasks import judge_task
        try:
            result = judge_task(self, registration, case, ticket, on_progress=on_progress)
            emit_progress(on_progress, stage='judge', status='succeeded',
                detail='Validated Input artifacts', artifact_directory=str(ticket.directory),
                sdk_run_id=result.run_id, event_timing='artifact_replay',
                **self._identity(registration, phase='judge', case_index=case.case_index, case_id=case.case_id))
            replay_input_events(ticket.directory, result, on_step_start, on_step_complete, on_step_failure)
            return result
        except BaseException as exc:
            if not getattr(exc, 'artifacts', None):
                host = json.loads((ticket.directory / 'run.json').read_text(encoding='utf-8'))
                exc.artifacts = collect_artifacts(ticket.directory, {**host, 'validation': 'failed'},
                                                  environ=self.environ)
                exc.artifacts['recovery'] = {'action': 'blocked', 'automatic': False,
                    'allow_replay': False, 'reason': str(exc)}
            raise

    def run_case(self, registration, case: PreparedCase, *, on_progress=None,
                 on_step_start=None, on_step_complete=None, on_step_failure=None,
                 _defer_judge=False) -> BenchmarkResult:
        """Execute only the requested prepared Case, without a mutable cursor."""
        self.control.check()
        self.validate_sdk(registration)
        if not isinstance(case, PreparedCase):
            raise TypeError('run_case requires a PreparedCase')
        if case.case_index >= registration.case_count:
            raise ValueError('Prepared Case index exceeds the registered Case count')
        if (case.case_id is None or case.content_sha256 is None or case.artifact_path is None
                or case.artifact_sha256 is None):
            raise ValueError('KUMA requires a prepared Case ID, content digest, artifact path and artifact digest')
        if not case.artifact_path.is_file() or case.artifact_path.is_symlink():
            raise ValueError(f'Prepared Case artifact is missing or linked: {case.artifact_path}')
        if artifact_digest(case.artifact_path, self.control) != case.artifact_sha256:
            raise ValueError('Prepared SDK Case artifact was modified after preparation')
        identity = self._identity(registration, phase='execute', case_index=case.case_index,
                                  case_id=case.case_id)
        directory = self._evaluate(
            registration, output=self.output, environ=self.environ,
            timeout=self.timeout, max_steps=self.max_steps, case_artifact=case.artifact_path,
            safe_case_replay=self.recovery_capabilities(registration).safe_case_replay,
            expected_case_id=case.case_id, expected_content_sha256=case.content_sha256,
            expected_environment_sha256=case.environment_sha256,
            trace_sink=self.trace_sink, trace_max_bytes=self.trace_max_bytes,
            **self._runtime_options(identity),
            **({'defer_judge': True} if _defer_judge else {}),
            on_artifacts_ready=lambda path: self._artifacts_ready(
                registration, on_progress, path, identity, 'Live artifacts available'))
        try:
            self.control.check()
            if _defer_judge:
                from .judge_tasks import prepare_task
                host = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
                if host.get('status') != 'succeeded':
                    raise evaluation_failure(directory, 'Container execution or SDK submission failed',
                                             environ=self.environ)
                ticket = prepare_task(directory, case, environ=self.environ)
                emit_progress(on_progress, stage='judge_queue', status='started',
                    detail='Agent execution and Docker cleanup complete; Judge queued',
                    artifact_directory=str(directory), artifact_run_id=directory.name,
                    case_count=registration.case_count, **{**identity, 'phase': 'judge'})
                return ticket
            result = read_result(directory, registration.agent_id, provider_mode=self.provider_mode)
            executed = json.loads((directory / 'evaluation/case.json').read_text())
            if executed['case_id'] != case.case_id:
                raise RuntimeError('Executed Case does not match the prepared Case ID')
            if case_content_sha256(executed) != case.content_sha256:
                raise RuntimeError('Executed Case content does not match the prepared Case')
            emit_progress(
                on_progress, stage='benchmark_execution', status='succeeded',
                detail='Validated Input artifacts', artifact_directory=str(directory),
                artifact_run_id=directory.name, sdk_run_id=result.run_id,
                event_timing='artifact_replay', case_count=registration.case_count, **identity,
            )
            replay_input_events(directory, result, on_step_start, on_step_complete, on_step_failure)
            return result
        except Exception as exc:
            status = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
            status['status'] = 'failed'
            exc.artifacts = collect_artifacts(directory, status, environ=self.environ)
            Artifacts(directory, environ=self.environ).save('run.json', {
                **status, 'status': 'cancelled' if self.control.cancelled else 'failed',
                'validation': 'failed', 'error_type': type(exc).__name__, 'error': str(exc),
                'artifacts': exc.artifacts,
            })
            raise


def replay_input_events(directory, result, on_start, on_complete, on_failure):
    """Emit recorded success/failure callbacks in the original Case Input order."""
    case = json.loads(artifact_path(directory, 'evaluation/case.json').read_text(encoding='utf-8'))
    outcomes = {step.input_id: (step, on_complete) for step in result.steps}
    outcomes.update({failure.input_id: (failure, on_failure) for failure in result.failures})
    for item in case['inputs']:
        outcome, callback = outcomes[item['input_id']]
        if on_start:
            on_start(result.agent_id, outcome.input_id, outcome.payload)
        if callback:
            callback(result.agent_id, outcome)


def read_result(directory, agent_id, *, recovered_report=None, provider_mode='official-container'):
    """Validate persisted artifacts or a recovered report before publishing it.

    A recovered candidate still requires original host trace acceptance, cleanup,
    complete Input/output/submission/evidence identity and report identity.
    Committed native failures retain their errors independently of Judge delivery.
    A report alone cannot establish acceptance or successful Agent execution.
    """
    def read(relative):
        path = artifact_path(directory, relative)
        return json.loads(path.read_text(encoding='utf-8'))
    host = read('run.json')
    summary = read('evaluation/manifest.json')
    if recovered_report is not None:
        if host.get('host_trace_validation') != 'succeeded' or host.get('cleanup_status') != 'succeeded':
            raise ValueError('Recovery requires original cleanup and host trace acceptance')
        host = {**host, 'status': 'succeeded'}
    # Older host Judge tasks wrote status=failed for a committed native failure.
    # Reconcile those only with original host gates, never from the verdict alone.
    accepted_failure = (host.get('status') == 'failed' and summary.get('execution') == 'failed'
                        and host.get('exit_code') in (None, 0)
                        and host.get('cleanup_status') == 'succeeded'
                        and host.get('host_trace_validation') == 'succeeded'
                        and host_acceptance(host) == 'accepted')
    if (host.get('agent_id') != agent_id or host.get('run_id') != directory.name
            or host_acceptance(host) == 'rejected'
            or (host.get('status') != 'succeeded' and not accepted_failure)):
        raise evaluation_failure(directory, 'Container evaluation did not complete')
    if recovered_report is not None:
        summary = {**summary, 'judge': 'received', 'phase': 'finished'}
    if summary.get('execution') not in ('succeeded', 'failed'):
        raise RuntimeError(f'Incomplete execution; artifacts: {directory}')
    for key, expected in {'otel':'complete', 'submission':'committed',
                           'evidence':'captured', 'judge':'received', 'phase':'finished'}.items():
        if summary.get(key) != expected:
            raise RuntimeError(f'Incomplete {key}; artifacts: {directory}')
    case = read('evaluation/case.json')
    report = read('evaluation/judge/report.json') if recovered_report is None else recovered_report
    if report.get('status') not in ('pass', 'issue', 'insufficient_evidence'):
        raise ValueError('Invalid Judge verdict')
    if (case['case_id'] != summary['case_id'] or report['run_id'] != summary['run_id']
        or report.get('extensions', {}).get('case_id') != summary['case_id']):
        raise RuntimeError('Case / Judge identity mismatch')
    expected_ids = [item['input_id'] for item in case['inputs']]
    if not expected_ids or [s['input_id'] for s in summary['steps']] != expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise RuntimeError('Incomplete or duplicate submitted Inputs')
    steps, failures = [], []
    for step, expected_input in zip(summary['steps'], case['inputs']):
        prefix = 'evaluation/' + step['directory']
        item, result, submission = (read(f'{prefix}/{name}.json') for name in ('input', 'result', 'submission'))
        request = read(f'{prefix}/request.json')
        succeeded = result.get('status') == 'succeeded'
        submitted_status = {'succeeded': 'completed', 'failed': 'failed', 'timeout': 'timeout',
                            'cancelled': 'aborted', 'aborted': 'aborted'}.get(result.get('status'))
        if (result.get('schema') != 'abb.result.v1' or submitted_status is None
            or submission.get('status') != submitted_status or request.get('agent_id') != agent_id
            or request.get('session_id') != summary['run_id']
            or result['agent_id'] != agent_id or result['run_id'] != request['run_id']
            or item['input_id'] != step['input_id'] or submission.get('output') != result.get('output')
            or (succeeded and 'output' not in result)
            or item.get('payload') != expected_input.get('payload')
            or (not succeeded and submission.get('error') != result.get('error'))
            or not step['committed']):
            raise RuntimeError('Input / output / submission identity mismatch')
        if read(f'{prefix}/otel-status.json').get('status') != 'complete':
            raise RuntimeError('Incomplete OTel artifacts')
        capture = submission.get('capture_status', {}).get('traces', {})
        if capture.get('status') not in ('complete', 'partial') or not isinstance(read(f'{prefix}/evidence.json'), dict):
            raise RuntimeError('SDK trace capture was not recorded; inspect capture-status.json')
        if succeeded:
            steps.append(BenchmarkStepResult(item['input_id'], item['payload'],
                         AdapterInvocation(result['output'], result.get('raw_output'))))
        else:
            failures.append(BenchmarkStepFailure(item['input_id'], item['payload'],
                result.get('error_type') or 'AgentExecutionError', result.get('error') or '',
                result.get('output'), result.get('raw_output')))
    if (summary['execution'] == 'failed') != bool(failures):
        raise RuntimeError('Execution summary does not match the submitted Inputs')
    normalized = Report(report['status'], report.get('confidence'), tuple(report.get('issues', [])),
                        tuple(report.get('evidence_gaps', [])), report['report_id'], report['run_id'],
                        {**report.get('extensions', {}), 'abb_artifact_directory': str(directory)})
    return BenchmarkResult(agent_id, 'container-' + 'sdk', summary['run_id'], 'report_ready',
                           normalized, tuple(steps), len(summary['steps']), provider_mode,
                           evidence_status=summary['evidence'], host_acceptance='accepted',
                           host_trace_validation=host.get('host_trace_validation', 'unknown'),
                           failures=tuple(failures))
