"""Shared container Case executor for run, certify and the evaluate alias."""
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from agentbench.adapter import AdapterInvocation
from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.progress import emit_progress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.runtime.contracts.execution import RunControl
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.contracts import PreparedCase, PreparedCaseBatch, RunnerRecoveryCapabilities
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.common.input_binding import validate_input_contract

from .service import evaluate
from .diagnostics import evaluation_failure, collect_artifacts
from .configuration import request_options, api_key
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
        except ValueError as exc:
            raise ProviderSelectionError(str(exc)) from exc
        for relative in ('evaluation/profile.md', 'evaluation/input-contract.json'):
            if not (registration.path / relative).is_file():
                raise ProviderSelectionError(f'Missing Agent evaluation file: {relative}')
        try:
            validate_input_contract(registration.path / 'evaluation/input-contract.json')
        except ValueError as exc:
            raise ProviderSelectionError(str(exc)) from exc
        return 'official-container'

    def recovery_capabilities(self, registration) -> RunnerRecoveryCapabilities:
        """Combine public request recovery with an explicit Agent replay promise."""
        from agentbench.sdk.common.replay import safe_case_replay
        return RunnerRecoveryCapabilities(safe_case_replay(registration), resume_judgment=True)

    def prepare_cases(self, registration, *, on_progress=None) -> tuple[PreparedCase, ...]:
        """Legacy API: require the complete imported/generated selection."""
        return prepare_batch(self, registration, evaluator=evaluate,
                             on_progress=on_progress, allow_partial=False).cases

    def prepare_case_batch(self, registration, *, case_indices=None,
                           on_progress=None) -> PreparedCaseBatch:
        """Return successful Cases, failures and unattempted original slot IDs.

        ``case_indices`` selects only missing zero-based slots. Complete saved
        collection imports remain strict; other generated slots can survive a
        single generation failure. This method never retries a failed request.
        """
        return prepare_batch(self, registration, evaluator=evaluate,
                             case_indices=case_indices, on_progress=on_progress)

    def recover_case(self, registration, case: PreparedCase, *, previous_result,
                     on_progress=None, on_step_start=None, on_step_complete=None,
                     on_step_failure=None) -> BenchmarkResult:
        """Resume the original Judge request and validate its unchanged evidence."""
        from .recovery_execution import recover_case
        try:
            return recover_case(self, registration, case, previous_result=previous_result,
                                validator=read_result, on_progress=on_progress)
        except Exception as exc:
            if not getattr(exc, 'artifacts', None):
                exc.artifacts = {**(previous_result.artifacts or {}), 'recovery': {
                    'action': 'blocked', 'automatic': False, 'reason': str(exc)}}
            raise

    def run_case(self, registration, case: PreparedCase, *, on_progress=None,
                 on_step_start=None, on_step_complete=None, on_step_failure=None) -> BenchmarkResult:
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
        directory = evaluate(
            registration, output=self.output, environ=self.environ,
            timeout=self.timeout, max_steps=self.max_steps, case_artifact=case.artifact_path,
            safe_case_replay=self.recovery_capabilities(registration).safe_case_replay,
            expected_case_id=case.case_id, expected_content_sha256=case.content_sha256,
            trace_sink=self.trace_sink, trace_max_bytes=self.trace_max_bytes,
            **self._runtime_options(identity),
            on_artifacts_ready=lambda path: self._artifacts_ready(
                registration, on_progress, path, identity, 'Live artifacts available'))
        try:
            self.control.check()
            result = read_result(directory, registration.agent_id)
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
            for step in result.steps:
                if on_step_start:
                    on_step_start(registration.agent_id, step.input_id, step.payload)
                if on_step_complete:
                    on_step_complete(registration.agent_id, step)
            return result
        except Exception as exc:
            status = json.loads((directory / 'run.json').read_text())
            status['status'] = 'failed'
            exc.artifacts = collect_artifacts(directory, status, environ=self.environ)
            Artifacts(directory, environ=self.environ).save('run.json', {
                **status, 'status': 'cancelled' if self.control.cancelled else 'failed',
                'validation': 'failed', 'error_type': type(exc).__name__, 'error': str(exc),
                'artifacts': exc.artifacts,
            })
            raise


def read_result(directory, agent_id, *, recovered_report=None):
    """Validate persisted artifacts or a recovered report before publishing it.

    A recovered candidate still requires original host trace acceptance, cleanup,
    complete Input/output/submission/evidence identity and report identity. This
    read-only path never promotes a failed host status merely because of a report.
    """
    def read(relative):
        candidate = directory / relative
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(directory.resolve()) or candidate.is_symlink():
            raise ValueError('Result path outside run')
        return json.loads(path.read_text(encoding='utf-8'))
    host = read('run.json')
    if recovered_report is not None:
        if host.get('host_trace_validation') != 'succeeded' or host.get('cleanup_status') != 'succeeded':
            raise ValueError('Recovery requires original cleanup and host trace acceptance')
        host = {**host, 'status': 'succeeded'}
    if host.get('agent_id') != agent_id or host.get('run_id') != directory.name or host.get('status') != 'succeeded':
        raise evaluation_failure(directory, 'Container evaluation did not complete')
    summary = read('evaluation/manifest.json')
    if recovered_report is not None:
        summary = {**summary, 'judge': 'received', 'phase': 'finished'}
    for key, expected in {'execution':'succeeded', 'otel':'complete', 'submission':'committed',
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
    steps = []
    for step in summary['steps']:
        prefix = 'evaluation/' + step['directory']
        item, result, submission = (read(f'{prefix}/{name}.json') for name in ('input', 'result', 'submission'))
        request = read(f'{prefix}/request.json')
        if (result.get('schema') != 'abb.result.v1' or result.get('status') != 'succeeded'
            or submission.get('status') != 'completed' or request.get('agent_id') != agent_id
            or request.get('session_id') != summary['run_id']
            or result['agent_id'] != agent_id or result['run_id'] != request['run_id']
            or item['input_id'] != step['input_id'] or submission['output'] != result['output']
            or not step['committed']):
            raise RuntimeError('Input / output / submission identity mismatch')
        if read(f'{prefix}/otel-status.json').get('status') != 'complete':
            raise RuntimeError('Incomplete OTel artifacts')
        capture = submission.get('capture_status', {}).get('traces', {})
        if capture.get('status') not in ('complete', 'partial') or not isinstance(read(f'{prefix}/evidence.json'), dict):
            raise RuntimeError('SDK trace capture was not recorded; inspect capture-status.json')
        value = BenchmarkStepResult(item['input_id'], item['payload'],
                                   AdapterInvocation(result['output'], result.get('raw_output')))
        steps.append(value)
    normalized = Report(report['status'], report.get('confidence'), tuple(report.get('issues', [])),
                        tuple(report.get('evidence_gaps', [])), report['report_id'], report['run_id'],
                        {**report.get('extensions', {}), 'abb_artifact_directory': str(directory)})
    return BenchmarkResult(agent_id, 'container-' + 'sdk', summary['run_id'], 'report_ready',
                           normalized, tuple(steps), len(steps), 'official-container')
