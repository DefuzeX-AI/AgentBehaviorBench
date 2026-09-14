"""Shared container Case executor for run, certify and the evaluate alias."""
import json
import shutil
import math
import os
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from agentbench.adapter import AdapterInvocation
from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.progress import emit_progress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.runtime.contracts.execution import RunControl
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.contracts import PreparedCase
from agentbench.sdk.common.case_identity import case_content_sha256

from .service import evaluate
from .diagnostics import evaluation_failure, collect_artifacts


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
    """Prepare a complete Case batch or execute one explicitly selected Case."""

    def __init__(self, *, environ=None, options=None, trace_sink=None, trace_max_bytes=262144,
                 control=None, build_coordinator=None, job_context=None,
                 runtime_services=None):
        self.environ = dict(os.environ if environ is None else environ)
        options = dict(options or {})
        unknown = set(options) - {'output', 'timeout', 'max_steps', 'case_collection'}
        if unknown:
            raise ProviderSelectionError(f'Unsupported container evaluation options: {sorted(unknown)}')
        self.output = Path(options.get('output', 'results/observe'))
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
                    runtime_services=self.runtime_services, identity=identity)

    def _artifacts_ready(self, registration, on_progress, path, identity, detail):
        emit_progress(
            on_progress, stage='case_generation' if identity['phase'] == 'generate' else 'benchmark_execution',
            status='started', detail=detail, artifact_directory=str(path), artifact_run_id=path.name,
            case_count=registration.case_count, **identity,
        )

    def validate_sdk(self, registration):
        if not (self.environ.get('KUMA_API_KEY') or self.environ.get('DEFUZEX_API_KEY')):
            raise ProviderSelectionError('KUMA_API_KEY or DEFUZEX_API_KEY is required')
        for relative in ('evaluation/profile.md', 'evaluation/input-contract.json'):
            if not (registration.path / relative).is_file():
                raise ProviderSelectionError(f'Missing Agent evaluation file: {relative}')
        return 'official-container'

    # generate cases
    def prepare_cases(self, registration, *, on_progress=None) -> tuple[PreparedCase, ...]:
        """Generate/import and validate the entire immutable selection once."""
        from .generation import validate_collection

        self.control.check()
        self.validate_sdk(registration)

        # 生成n个case
        count = registration.case_count
        identity = self._identity(registration, phase='generate', case_index=None, case_id=None)

        # 并没有提前拿着生成好的case的情况下，我们走生成case
        if self.case_collection is None:
            directory = evaluate(
                registration, output=self.output, environ=self.environ,
                timeout=self.timeout, max_steps=self.max_steps, generation_count=count,
                trace_sink=self.trace_sink, trace_max_bytes=self.trace_max_bytes,
                **self._runtime_options(identity),
                on_artifacts_ready=lambda path: self._artifacts_ready(
                    registration, on_progress, path, identity, f'Preparing {count} distinct Cases'))
        else:
            # 如果提前拿着生成好的case的情况下，我们走导入case
            directory = self.output.resolve() / uuid4().hex
            files = Artifacts(directory, environ=self.environ)
            files.save('run.json', {**identity, 'schema': 'abb.case_collection.import.v1',
                                   'run_id': directory.name, 'artifact_run_id': directory.name,
                                   'status': 'running', 'source': str(self.case_collection.resolve())})
        
        files = Artifacts(directory, environ=self.environ)
        try:
            self.control.check()
            if self.case_collection is None:
                status = json.loads((directory / 'run.json').read_text())
                if status.get('status') != 'succeeded':
                    raise evaluation_failure(directory, 'Case batch generation failed', environ=self.environ)
                collection = json.loads((directory / 'evaluation/case-collection.json').read_text())
            else:
                collection = json.loads(self.case_collection.read_text())
                validate_collection(collection, count=count)
                source_cases = self.case_collection.resolve().parent / 'cases'
                target_cases = directory / 'evaluation/cases'
                target_cases.mkdir(parents=True)
                for entry in collection['cases']:
                    self.control.check()
                    source = _collection_artifact(source_cases, entry['artifact'])
                    shutil.copyfile(source, target_cases / source.name)
                files.save('evaluation/case-collection.json', collection)
            validate_collection(collection, count=count)
            prepared = []
            artifact_hashes = set()
            for index, entry in enumerate(collection['cases']):
                self.control.check()
                source = _collection_artifact(directory / 'evaluation/cases', entry['artifact'])
                artifact = json.loads(source.read_text(encoding='utf-8'))
                if (not isinstance(artifact, dict) or not artifact.get('schema_version')
                        or not isinstance(artifact.get('case'), dict)):
                    raise ValueError('Invalid saved SDK Case artifact')
                path, artifact_hash = _freeze_artifact(
                    source, directory / 'evaluation/prepared-cases' / f'case-{index + 1:04d}.json',
                    self.control)
                if artifact_hash in artifact_hashes:
                    raise ValueError('Case collection references duplicate saved artifact content')
                artifact_hashes.add(artifact_hash)
                prepared.append(PreparedCase(index, entry['case_id'], path,
                                             entry['content_sha256'], artifact_hash))
            files.save('evaluation/batch-selection.json', {
                'requested_count': count, 'accepted_count': count, 'status': 'accepted'})
            status = json.loads((directory / 'run.json').read_text())
            files.save('run.json', {**status, 'status': 'succeeded', 'validation': 'succeeded'})
            return tuple(prepared)
        except Exception as exc:
            files.save('evaluation/batch-selection.json', {
                'requested_count': count, 'accepted_count': 0, 'status': 'rejected', 'error': str(exc)})
            status = json.loads((directory / 'run.json').read_text())
            files.save('run.json', {**status, 'status': 'cancelled' if self.control.cancelled else 'failed',
                                   'validation': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)})
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
        if _artifact_digest(case.artifact_path, self.control) != case.artifact_sha256:
            raise ValueError('Prepared SDK Case artifact was modified after preparation')
        identity = self._identity(registration, phase='execute', case_index=case.case_index,
                                  case_id=case.case_id)
        directory = evaluate(
            registration, output=self.output, environ=self.environ,
            timeout=self.timeout, max_steps=self.max_steps, case_artifact=case.artifact_path,
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


def _collection_artifact(directory: Path, reference: str) -> Path:
    """Resolve an exported Case file without accepting links or path aliases."""
    path = directory / Path(reference).name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
        raise ValueError(f'Case collection is missing its saved Case artifact: {reference}')
    return path.resolve()


def _freeze_artifact(source: Path, target: Path, control: RunControl) -> tuple[Path, str]:
    """Copy the SDK wire bytes and return their explicit integrity digest."""
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    stream = tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False)
    temporary = Path(stream.name)
    try:
        with source.open('rb') as incoming, stream:
            while block := incoming.read(1024 * 1024):
                control.check()
                digest.update(block)
                stream.write(block)
        temporary.chmod(0o444)
        temporary.replace(target)
        return target.resolve(), digest.hexdigest()
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_digest(path: Path, control: RunControl) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            control.check()
            digest.update(block)
    return digest.hexdigest()


def read_result(directory, agent_id):
    """Validate the completed artifact contract on the trusted host."""
    def read(relative):
        candidate = directory / relative
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(directory.resolve()) or candidate.is_symlink():
            raise ValueError('Result path outside run')
        return json.loads(path.read_text(encoding='utf-8'))
    host = read('run.json')
    if host.get('agent_id') != agent_id or host.get('run_id') != directory.name or host.get('status') != 'succeeded':
        raise evaluation_failure(directory, 'Container evaluation did not complete')
    summary = read('evaluation/manifest.json')
    for key, expected in {'execution':'succeeded', 'otel':'complete', 'submission':'committed',
                           'evidence':'captured', 'judge':'received', 'phase':'finished'}.items():
        if summary.get(key) != expected:
            raise RuntimeError(f'Incomplete {key}; artifacts: {directory}')
    case = read('evaluation/case.json')
    report = read('evaluation/judge/report.json')
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
        if not read(f'{prefix}/evidence.json').get('spans'):
            raise RuntimeError('Missing SDK span evidence')
        value = BenchmarkStepResult(item['input_id'], item['payload'],
                                   AdapterInvocation(result['output'], result.get('raw_output')))
        steps.append(value)
    normalized = Report(report['status'], report.get('confidence'), tuple(report.get('issues', [])),
                        tuple(report.get('evidence_gaps', [])), report['report_id'], report['run_id'],
                        {**report.get('extensions', {}), 'abb_artifact_directory': str(directory)})
    return BenchmarkResult(agent_id, 'container-' + 'sdk', summary['run_id'], 'report_ready',
                           normalized, tuple(steps), len(steps), 'official-container')
