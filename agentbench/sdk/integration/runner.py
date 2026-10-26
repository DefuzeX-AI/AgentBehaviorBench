"""Default EvaluationRunner: prepare durable Cases, execute and validate one Run."""
from dataclasses import replace
import json
import math
from pathlib import Path

from agentbench.adapter import AdapterInvocation
from agentbench.harness.progress import emit_progress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult, BenchmarkStepFailure
from agentbench.sdk.common.workspace import workspace_digest
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.observe.store import redact
from agentbench.sdk.contracts import PreparedCase
from .cases import case_bytes, digest, unpack_case
from .execution import run_evaluation
from .run import Report


def read(path):
    from agentbench.observe.artifact_paths import resolve_artifact_path
    path = resolve_artifact_path(path)
    if path.is_symlink():
        raise ValueError('SDK artifacts must not be links')
    return json.loads(path.read_bytes())


def accepted(directory, *, execution):
    host = read(directory / 'run.json')
    required = ['status', 'cleanup_status'] + (['host_trace_validation'] if execution else [])
    if any(host.get(key) != 'succeeded' for key in required):
        path = directory / 'error.json'
        sdk_error = read(path) if Path(path).is_file() else {}
        detail = sdk_error.get('error') or 'inspect retained artifacts'
        error = RuntimeError('SDK execution, evidence validation or cleanup failed: ' + detail)
        error.artifacts = {'directory': str(directory), **host, 'sdk_error': sdk_error}
        raise error
    return host


class ContainerSDKRunner:
    def __init__(self, plugin, *, context, options):
        self.plugin, self.context = plugin, context
        options = dict(options)
        self.output = Path(options.pop('output', 'results/observe'))
        self.timeout = options.pop('timeout', 2400)
        if (isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float))
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ValueError('SDK timeout must be a positive finite number')
        self.sdk_options = options
        limit = self.sdk_options.get('max_steps')
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError('max_steps must be a positive integer')
        if set(self.sdk_options) & {'case', 'repo_path', 'agent_root', 'storage_path', 'case_index', 'evidence'}:
            raise ValueError('SDK options cannot override worker-owned arguments')
        if redact(self.sdk_options, Artifacts(self.output, environ=context.environ).secrets) != self.sdk_options:
            raise ValueError('SDK credentials belong in worker_environment, not sdk_options')
        case_bytes(self.sdk_options)  # Fail before startup for nonportable options.
        self.directory = None

    def validate_sdk(self, registration):
        self._check()
        if not self.plugin.requirements.is_file() or self.plugin.requirements.is_symlink():
            raise ValueError('SDK requirements file is missing or linked')
        for name in self.plugin.documents:
            path = registration.path / name
            if (not name or Path(name).is_absolute() or '..' in Path(name).parts
                    or not path.resolve().is_relative_to(registration.path.resolve())
                    or not path.exists() or path.is_symlink()):
                raise ValueError(f'SDK document is missing or unsafe: {name}')
        for name in self.plugin.worker_environment:
            if not isinstance(name, str) or not name.strip():
                raise ValueError('SDK environment names must be non-empty strings')
        return 'sdk-container'

    def _check(self):
        if self.context.control is not None:
            self.context.control.check()

    def _settings(self, registration, **values):
        return dict(sdk_factory=self.plugin.create_run, sdk_options=self.sdk_options,
                    execution_only=getattr(self.plugin, 'execution_only', False),
                    agent_id=registration.agent_id, framework=registration.framework, **values)

    def _run(self, registration, *, settings, context, on_progress, **kwargs):
        def ready(directory):
            self.directory = directory
            emit_progress(on_progress, stage='case_generation' if settings['mode'] in ('generate', 'context')
                          else 'benchmark_execution', status='started',
                          agent_id=registration.agent_id, artifact_directory=str(directory),
                          detail='SDK artifacts available')
        return run_evaluation(registration, context=context, output=self.output,
            settings=settings, stage_agent=self.plugin.stage_agent, timeout=self.timeout,
            on_artifacts_ready=ready, **kwargs)

    def prepare_cases(self, registration, *, on_progress=None):
        self.validate_sdk(registration)
        if type(registration.case_count) is not int or registration.case_count < 1:
            raise ValueError('Case count must be a positive integer')
        indices = tuple(range(registration.case_count))
        directory = self._run(registration, context=self.context, on_progress=on_progress,
            settings=self._settings(registration, mode='generate', case_indices=indices),
            execute_agent=False, generation_indices=indices)
        accepted(directory, execution=False)
        collection = read(directory / 'case-collection.json')
        if (not isinstance(collection, list) or len(collection) != len(indices)
                or [entry.get('case_index') for entry in collection] != list(indices)):
            raise ValueError('SDK generation returned an incomplete Case collection')
        cases, identities = [], set()
        for index, entry in enumerate(collection):
            self._check()
            relative = f'cases/{index:04d}.json'
            if entry.get('artifact') != relative:
                raise ValueError('Unexpected generated Case artifact path')
            path = directory / relative
            document = read(path)
            case = unpack_case(document, factory=self.plugin.create_run, index=index)
            if (entry.get('artifact_sha256') != digest(Path(path).read_bytes())
                    or entry.get('case_id') != case['case_id']
                    or entry.get('content_sha256') != digest(case_bytes(case))
                    or case['case_id'] in identities):
                raise ValueError('Generated Case identity mismatch or duplicate')
            identities.add(case['case_id'])
            if self.context.artifacts is not None:
                path = self.context.artifacts.case(registration.agent_id, index).publish_case(case_bytes(document))
            workspace = document.get('workspace')
            cases.append(PreparedCase(index, case['case_id'], Path(path).resolve(),
                digest(case_bytes(case)), digest(Path(path).read_bytes()),
                workspace_digest(workspace) if workspace is not None else None))
        emit_progress(on_progress, stage='case_generation', status='succeeded',
                      agent_id=registration.agent_id, detail=f'Prepared {len(cases)} Cases')
        return tuple(cases)

    def run_case(self, registration, case, *, on_progress=None, on_step_start=None,
                 on_step_complete=None, on_step_failure=None):
        self.validate_sdk(registration)
        if (not isinstance(case, PreparedCase) or case.artifact_path is None
                or case.case_index >= registration.case_count):
            raise ValueError('Default SDK execution requires a prepared Case')
        document = read(case.artifact_path)
        source_index = document.get('case_index') if getattr(self.plugin, 'execution_only', False) else case.case_index
        snapshot = unpack_case(document, factory=self.plugin.create_run, index=source_index)
        workspace = document.get('workspace')
        if (digest(Path(case.artifact_path).read_bytes()) != case.artifact_sha256
                or digest(case_bytes(snapshot)) != case.content_sha256
                or snapshot['case_id'] != case.case_id
                or (workspace_digest(workspace) if workspace is not None else None) != case.environment_sha256):
            raise ValueError('Prepared Case was modified after generation')
        context = replace(self.context, job_context={**dict(self.context.job_context or {}),
                          'case_index': case.case_index, 'case_id': case.case_id})
        directory = self._run(registration, context=context, on_progress=on_progress,
            settings=self._settings(registration, mode='execute', case_index=case.case_index,
                source_case_index=source_index,
                expected_case_id=case.case_id, expected_content_sha256=case.content_sha256,
                expected_artifact_sha256=case.artifact_sha256),
            private_files={'case.json': case.artifact_path},
            expected_environment_sha256=case.environment_sha256, require_workspace_identity=True)
        try:
            result = self._read_result(directory, registration, case, document)
        except Exception as exc:
            if (getattr(exc, 'artifacts', None) or {}).get('phase') == 'judge':
                # Judge delivery must never rewrite accepted Agent execution.
                raise
            host = read(directory / 'run.json')
            host.update(status='failed', validation='failed', validation_error=str(exc))
            Artifacts(directory, environ=self.context.environ).save('run.json', host)
            exc.artifacts = {'directory': str(directory), **host}
            raise
        # Persisted step events, like Kuma's host callbacks, are replayed only
        # after host validation. SDKs do not implement a second callback loop.
        by_id = {step.input_id: (step, on_step_complete) for step in result.steps}
        by_id.update({step.input_id: (step, on_step_failure) for step in result.failures})
        for entry in read(directory / 'manifest.json')['steps']:
            step, callback = by_id[entry['input_id']]
            if on_step_start is not None:
                on_step_start(result.agent_id, step.input_id, step.payload)
            if callback is not None:
                callback(result.agent_id, step)
        emit_progress(on_progress, stage='benchmark_execution', status='succeeded',
                      agent_id=registration.agent_id, artifact_directory=str(directory),
                      detail='SDK execution and evidence validated')
        return result

    def _read_result(self, directory, registration, case, document):
        from agentbench.observe.artifact_paths import resolve_artifact_path
        host = accepted(directory, execution=True)
        root = directory
        manifest = read(root / 'manifest.json')
        unjudged = (getattr(self.plugin, 'execution_only', False)
                    and manifest.get('judge_delivery_status') == 'not_requested')
        report = None if unjudged else read(root / 'judge/report.json')
        if (host.get('agent_id') != registration.agent_id or host.get('case_id') != case.case_id
                or host.get('case_index') != case.case_index
                or manifest.get('schema') != 'abb.sdk.execution.v1'
                or manifest.get('status') != 'succeeded' or manifest.get('evidence') != 'complete'
                or manifest.get('case_id') != case.case_id or read(root / 'case.json') != document
                or not isinstance(manifest.get('run_id'), str) or not manifest['run_id']
                or type(manifest.get('history_count')) is not int or manifest['history_count'] < 0
                or (not unjudged and (not isinstance(report.get('status'), str) or not report['status']))):
            raise ValueError('SDK result identity or completion mismatch')
        steps, failures, seen = [], [], set()
        for index, entry in enumerate(manifest['steps'], 1):
            relative = f'steps/{index:04d}'
            if entry.get('directory') not in (relative, f'inputs/{index:04d}') or entry.get('submitted') is not True:
                raise ValueError('SDK step was not committed')
            item, request, output, submission = [read(root / relative / name) for name in (
                'input.json', 'request.json', 'result.json', 'submission.json')]
            if (item['input_id'] in seen or item['input_id'] != entry['input_id']
                    or submission.get('input_id') != item['input_id'] or submission.get('submitted') is not True
                    or submission.get('result') != output or entry.get('status') != output.get('status')
                    or request.get('input') != item['payload']
                    or request.get('session_id') != manifest['run_id']
                    or request.get('agent_id') != registration.agent_id
                    or request.get('framework') != registration.framework
                    or request.get('observation_context') != {'case_id': case.case_id, 'input_id': item['input_id']}
                    or not request.get('run_id') or output.get('run_id') != request['run_id']
                    or read(root / relative / 'otel-status.json').get('status') != 'complete'
                    or not resolve_artifact_path(root / relative / 'spans.jsonl').is_file()):
                raise ValueError('SDK input, output, submission or evidence mismatch')
            seen.add(item['input_id'])
            if output['status'] == 'succeeded':
                steps.append(BenchmarkStepResult(item['input_id'], item['payload'],
                    AdapterInvocation(output['output'], output.get('raw_output'))))
            elif output['status'] in ('failed', 'timeout', 'cancelled', 'aborted'):
                failures.append(BenchmarkStepFailure(item['input_id'], item['payload'],
                    output.get('error_type') or 'AgentExecutionError', output.get('error') or '',
                    output.get('output'), output.get('raw_output')))
            else:
                raise ValueError('Unknown Agent result status')
        if not seen:
            raise ValueError('SDK result has no executed inputs')
        normalized = None if unjudged else Report(report['status'], report.get('confidence'),
                            tuple(report['issues']), tuple(report['evidence_gaps']))
        return BenchmarkResult(registration.agent_id, registration.framework, manifest['run_id'],
            manifest['run_state'], normalized, tuple(steps), manifest['history_count'], provider_mode='sdk-container',
            evidence_status='captured', host_acceptance='accepted',
            host_trace_validation='succeeded', failures=tuple(failures),
            judge_delivery_status='not_requested' if unjudged else 'received')
