"""Shared container Case executor for run, certify and the evaluate alias."""
import json
import shutil
import math
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from agentbench.adapter import AdapterInvocation
from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.progress import emit_progress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.sdk.common.artifacts import Artifacts

from .service import evaluate


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
    """Formal KUMA runner retained behind the KUMA evaluation plugin."""

    def __init__(self, *, environ=None, options=None, trace_sink=None, trace_max_bytes=262144):
        self.environ = dict(os.environ if environ is None else environ)
        options = dict(options or {})
        unknown = set(options) - {'sdk_source', 'output', 'timeout', 'max_steps', 'case_collection'}
        if unknown:
            raise ProviderSelectionError(f'Unsupported container evaluation options: {sorted(unknown)}')
        self.sdk = Path(options.get('sdk_source', Path(__file__).resolve().parents[4] / 'Defuze-SDK'))
        self.output = Path(options.get('output', 'results/observe'))
        self.timeout = options.get('timeout', 2400)
        self.case_collection = Path(options['case_collection']) if options.get('case_collection') is not None else None
        self.max_steps = options.get('max_steps')
        if self.max_steps is not None and (type(self.max_steps) is not int or self.max_steps < 1):
            raise ProviderSelectionError('max_steps must be a positive integer')
        if (isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ProviderSelectionError('Container timeout must be a positive finite number')
        self.trace_sink = trace_sink
        self.trace_max_bytes = trace_max_bytes
        self._case_fingerprints = {}
        self._case_batches = {}

    def begin_suite(self, suite_id):
        """Scope generated-content deduplication to this requested test suite."""
        self._case_fingerprints = {}
        self._case_batches = {}

    def _prepare_batch(self, registration, on_progress):
        """Collect the Registry count completely, before any Agent execution."""
        count = getattr(registration, 'case_count', 1)
        if self.case_collection is not None:
            # Explicit reuse preserves the original collection and never generates. The
            # saved Case artifacts are read from a `cases` folder beside the collection.
            collection = json.loads(self.case_collection.read_text())
            directory = self.output.resolve() / uuid4().hex
            files = Artifacts(directory)
            files.save('evaluation/case-collection.json', collection)
            source_cases = self.case_collection.resolve().parent / 'cases'
            target_cases = directory / 'evaluation/cases'; target_cases.mkdir(parents=True, exist_ok=True)
            for entry in collection.get('cases', ()):
                name = Path(entry.get('artifact', '')).name
                if not name or not (source_cases / name).is_file():
                    raise RuntimeError(f'Case collection is missing its saved Case artifact: {name or entry}')
                shutil.copyfile(source_cases / name, target_cases / name)
            files.save('run.json', {'schema': 'abb.case_collection.import.v1',
                                   'status': 'succeeded', 'source': str(self.case_collection.resolve())})
        else:
            directory = evaluate(
                registration, output=self.output, sdk=self.sdk, environ=self.environ,
                timeout=self.timeout, max_steps=self.max_steps, generation_count=count,
                trace_sink=self.trace_sink, trace_max_bytes=self.trace_max_bytes,
                on_artifacts_ready=lambda path: emit_progress(
                    on_progress, stage='benchmark_execution', status='started',
                    agent_id=registration.agent_id, detail=f'Preparing {count} distinct Cases',
                    artifact_directory=str(path)))
            status = json.loads((directory / 'run.json').read_text())
            if status.get('status') != 'succeeded':
                raise RuntimeError(f'Case batch generation failed: {directory}')
        collection = json.loads((directory / 'evaluation/case-collection.json').read_text())
        from .generation import validate_collection
        files = Artifacts(directory)
        try:
            validate_collection(collection, count=count)
        except ValueError as exc:
            files.save('evaluation/batch-selection.json', {
                'requested_count': count, 'accepted_count': 0, 'status': 'rejected', 'error': str(exc)})
            status = json.loads((directory / 'run.json').read_text())
            files.save('run.json', {**status, 'status': 'failed', 'validation': 'failed'})
            raise RuntimeError(str(exc)) from exc
        self._case_batches[registration.agent_id] = {
            'collection': collection, 'next_index': 0, 'cases': directory / 'evaluation/cases'}
        Artifacts(directory).save('evaluation/batch-selection.json', {
            'requested_count': count, 'accepted_count': count, 'status': 'accepted'})
        return self._case_batches[registration.agent_id]

    def validate_sdk(self, registration):
        if not (self.environ.get('KUMA_API_KEY') or self.environ.get('DEFUZEX_API_KEY')):
            raise ProviderSelectionError('KUMA_API_KEY or DEFUZEX_API_KEY is required')
        for relative in ('evaluation/profile.md', 'evaluation/input-contract.json'):
            if not (registration.path / relative).is_file():
                raise ProviderSelectionError(f'Missing Agent evaluation file: {relative}')
        if not (self.sdk / 'src/kuma/__init__.py').is_file():
            raise ProviderSelectionError('Local KUMA SDK source unavailable')
        return 'official-container'

    def run_defuzex(self, *args, **kwargs):
        raise ProviderSelectionError('Legacy run_defuzex options are not supported by the default container core; use run()')

    validate_defuzex = run_defuzex

    def run(self, registration, *, on_progress=None, on_step_start=None,
            on_step_complete=None, on_step_failure=None):
        self.validate_sdk(registration)
        prepared = self._case_batches.get(registration.agent_id)
        if prepared is None:
            prepared = self._prepare_batch(registration, on_progress)
        index = prepared['next_index']
        if index >= len(prepared['collection']['cases']):
            raise RuntimeError('Generated Case batch is exhausted; start a new suite explicitly')
        prepared['next_index'] += 1
        entry = prepared['collection']['cases'][index]
        case_artifact = prepared['cases'] / Path(entry['artifact']).name
        if not case_artifact.is_file():
            raise RuntimeError(f'Prepared Case artifact is missing: {case_artifact}')
        directory = evaluate(registration, output=self.output, sdk=self.sdk,
                             environ=self.environ, timeout=self.timeout, max_steps=self.max_steps,
                             case_artifact=case_artifact,
                             excluded_cases=self._case_fingerprints.get(registration.agent_id, ()), trace_sink=self.trace_sink,
                             trace_max_bytes=self.trace_max_bytes,
                             on_artifacts_ready=lambda path: emit_progress(
                                 on_progress, stage='benchmark_execution', status='started',
                                 agent_id=registration.agent_id, detail='Live artifacts available',
                                 artifact_directory=str(path)))
        try:
            result = read_result(directory, registration.agent_id, on_step_start, on_step_complete)
            from agentbench.sdk.common.case_identity import case_content_sha256
            case = json.loads((directory / 'evaluation/case.json').read_text())
            if case['case_id'] != entry['case_id']:
                raise RuntimeError('Executed Case does not match the prepared collection entry')
            fingerprint = case_content_sha256(case)
            seen = self._case_fingerprints.setdefault(registration.agent_id, [])
            if fingerprint in seen:
                raise RuntimeError('SDK returned duplicate Case content; requested distinct Cases were not completed')
            seen.append(fingerprint)
            return result
        except Exception as exc:
            # Container exit zero is not certification: the host must accept its artifacts.
            Artifacts(directory).save('run.json', {
                'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
                'agent_id': registration.agent_id, 'status': 'failed',
                'validation': 'failed', 'error_type': type(exc).__name__,
            })
            raise


def read_result(directory, agent_id, on_step_start=None, on_step_complete=None):
    """Validate the completed artifact contract on the trusted host."""
    def read(relative):
        candidate = directory / relative
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(directory.resolve()) or candidate.is_symlink():
            raise ValueError('Result path outside run')
        return json.loads(path.read_text(encoding='utf-8'))
    host = read('run.json')
    if host.get('agent_id') != agent_id or host.get('run_id') != directory.name or host.get('status') != 'succeeded':
        raise RuntimeError(f'Container evaluation did not complete: {directory}')
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
    # Notify only after every Input passes validation, not during partial validation.
    for value in steps:
        # These are persisted completion notifications, not live timing events.
        if on_step_start:
            on_step_start(agent_id, value.input_id, value.payload)
        if on_step_complete:
            on_step_complete(agent_id, value)
    normalized = Report(report['status'], report.get('confidence'), tuple(report.get('issues', [])),
                        tuple(report.get('evidence_gaps', [])), report['report_id'], report['run_id'],
                        {**report.get('extensions', {}), 'abb_artifact_directory': str(directory)})
    return BenchmarkResult(agent_id, 'container-' + 'sdk', summary['run_id'], 'report_ready',
                           normalized, tuple(steps), len(steps), 'official-container')


# Compatibility for callers which imported the original implementation name.
ContainerBenchmarkRunner = KumaContainerRunner
