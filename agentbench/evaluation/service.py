"""One application API for Python, CLI and future transports.

Credentials are explicit host configuration. Calls never prompt or launch a UI.
Execution uses the existing Suite scheduler and immutable artifact store.
"""
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path

from agentbench.harness.registry import load_registry
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.codec import agent_to_json, case_from_json, case_to_json
from agentbench.harness.result import BenchmarkSuiteResult, SuiteAgentResult
from agentbench.observe.suite_reader import persisted_snapshot
from agentbench.observe.view_api import SuiteRunCatalogAPI
from agentbench.sdk.common.agent_context import load_agent_context
from agentbench.sdk.judges import execute_judge, validate_evidence, validate_response
from .configuration import runner_configuration
from .runner import build_trace_suite_runner


def suite_summary(result):
    return {'selected': result.selected_count, 'attempted': result.attempted_count,
            'passed': result.passed_count, 'failed': result.failed_count,
            'skipped': result.skipped_count, 'suite_passed': result.passed,
            'execution_status': result.execution_status, 'execution_counts': result.execution_counts,
            'case_execution_counts': result.case_execution_counts, 'judge_counts': result.judge_counts,
            'quality_gate': result.quality_gate, 'exit_code': result.exit_code}


def execute_registered(runner, agents, *, store=None, environ=None, **kwargs):
    """Bind durable Cases and artifacts identically for every transport."""
    from agentbench.harness import SuiteRunner
    from agentbench.sdk.integration.artifacts import FileArtifactStore
    if store is not None:
        kwargs['retain_case'] = store.retain_case
        if isinstance(runner, SuiteRunner):
            kwargs['artifact_store'] = FileArtifactStore(store.directory, environ=environ)
    return runner.run(agents, **kwargs)


class EvaluationService:
    def __init__(self, root, *, environ=None):
        self.root = Path(root).resolve()
        self.environ = dict(os.environ if environ is None else environ)

    def agent(self, agent_id):
        from agentbench.harness.registry import tomllib
        registration = load_registry(self.root / 'resources/registry.toml').find(agent_id)
        manifest = tomllib.loads((registration.path / 'agent.toml').read_text(encoding='utf-8'))
        return {'schema': 'abb.agent.info.v1', 'agent_id': agent_id,
                'display_name': manifest.get('display_name', agent_id),
                'source': {key: manifest.get('source', {}).get(key) for key in ('method', 'repository', 'revision')},
                'framework': registration.framework, 'status': registration.status,
                'case_count': registration.case_count, 'max_steps': registration.max_steps,
                'context': load_agent_context(registration.path / 'requirement.md', agent_id=agent_id)}

    def execute(self, agent_id, cases, *, results_dir=None, judge=None, model=None,
                timeout=2400, max_steps=None, concurrency=None, on_event=None):
        from agentbench.sdk import resolve_sdk
        from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
        from agentbench.harness.session.references import history_guard, register_suite_reference
        from agentbench.sdk.plugin.native.backend import validate_case
        if not isinstance(cases, list) or not cases:
            raise ValueError('Cases must be a non-empty list')
        context = self.agent(agent_id)['context']
        cases = [validate_case({**case, 'abb_agent_context': context}) for case in cases]
        registration = load_registry(self.root / 'resources/registry.toml').find(agent_id)
        registration = replace(registration, case_count=len(cases))
        options = {'cases': cases, 'timeout': timeout}
        if max_steps is not None:
            options['max_steps'] = max_steps
        if judge is not None:
            options['judge'] = judge
        runner = build_trace_suite_runner(max_bytes=DEFAULT_TRACE_MAX_BYTES, model=model,
            sdk_selection=resolve_sdk('native'), sdk_options=options,
            concurrency=concurrency, environ=self.environ)
        suite_id = runner.new_suite_id()
        parent = Path(results_dir) if results_dir is not None else self.root / 'results'
        with history_guard(self.root):
            store = SuiteStore.begin(parent / 'suites', suite_id, (registration,),
                configuration=runner_configuration(runner, (registration,)), environ=self.environ)
            try:
                register_suite_reference(store.directory, project_root=self.root)
            except BaseException:
                store.close()
                raise
        with store:
            def event(value):
                # retain_case has already durably recorded this event.
                if value.get('event') != 'case_prepared':
                    store.append(value)
                if on_event is not None:
                    on_event(value)
            try:
                result = execute_registered(runner, (registration,), suite_id=suite_id,
                    on_event=event, store=store, environ=self.environ)
                store.append({'event': 'suite_completed', 'summary': suite_summary(result)})
            except BaseException as exc:
                store.append({'event': 'suite_failed', 'error': {'type': type(exc).__name__,
                    'message': str(exc)}})
                raise
        return self.result(store.directory)

    def result(self, suite):
        directory = Path(suite).resolve()
        snapshot = persisted_snapshot(directory / 'events.json')
        if snapshot is None:
            raise ValueError('A canonical Suite directory is required')
        entries = SuiteRunCatalogAPI(directory / 'events.json').entries(snapshot=snapshot)
        return {'schema': 'abb.evaluation.result.v1', 'directory': str(directory),
                'suite': snapshot, 'runs': [meta for _, meta in entries.values() if meta.get('attempt_id')]}

    def _run(self, suite, run_id):
        entries = SuiteRunCatalogAPI(Path(suite) / 'events.json').entries()
        if run_id not in entries:
            raise ValueError('Run is not registered in this Suite')
        return entries[run_id]

    def evidence(self, suite, run_id):
        api, metadata = self._run(suite, run_id)
        request = api.read('evaluation/judge/request.json')
        if request is None:
            raise ValueError('Run has no retained Judge request')
        validate_evidence(request, api.directory)
        return {'schema': 'abb.evaluation.evidence.v1', 'run': metadata,
                'request': request, 'trajectory': api.spans(), 'evaluation': api.evaluation()}

    def attachment(self, suite, run_id, path):
        api, _ = self._run(suite, run_id)
        request = api.read('evaluation/judge/request.json')
        validate_evidence(request, api.directory)
        if path not in request['attachments']:
            raise ValueError('File is not a registered Judge attachment')
        return {'path': path, **request['attachments'][path],
                'content': api.file(path).read_text(encoding='utf-8')}

    def submit_judge(self, suite, run_id, response):
        from agentbench.harness.session.codec import RecoveredReport
        with SuiteStore.open(suite, environ=self.environ) as store:
            snapshot = store.snapshot()
            if snapshot['state'] != 'complete':
                raise ValueError('Finish execution before submitting an external Judge report')
            api, metadata = self._run(suite, run_id)
            request = api.read('evaluation/judge/request.json')
            validate_evidence(request, api.directory)
            validate_response(response, request)
            self._validate_submission(response, request)
            if request.get('judge') is not None:
                raise ValueError('Run already has an assigned Judge')
            job = next(j for j in snapshot['jobs'] if j['agent_id'] == metadata['agent'])
            case = next(c for c in job['cases'] if c['case_index'] == metadata['case_index'])
            attempt = next(a for a in case['attempts'] if a['attempt_id'] == metadata['attempt_id'])
            old = attempt.get('result') or {}
            if not old.get('benchmark') or attempt.get('host_acceptance') != 'accepted':
                raise ValueError('External judging requires host-accepted execution')
            saved = api.read('evaluation/judge/report.json')
            if saved is not None and saved != response:
                raise ValueError('A different Judge report already exists')
            if old['benchmark'].get('report') == response:
                return self.result(suite)
            # Use the same protocol, integrity checks, lock and persistence as providers.
            class Submitted:
                def judge(self, *args, **kwargs):
                    return deepcopy(response)
            execute_judge(Submitted(), request, directory=api.directory, environ=self.environ)
            safe = api.read('evaluation/judge/report.json')
            original = case_from_json(old)
            benchmark = replace(original.benchmark, report=RecoveredReport(safe), judge_delivery_status='received')
            updated = replace(original, benchmark=benchmark,
                              status='succeeded' if benchmark.passed else 'failed')
            value = case_to_json(updated)
            store.append({'event': 'case_completed', **value, 'case_result': value})
            # Refresh aggregates from current cases, preserving historical attempts.
            current = store.snapshot()
            items = []
            for entry in current['jobs']:
                outcomes = tuple(case_from_json(c['result']) for c in entry['cases'] if c.get('result'))
                if len(outcomes) != len(entry['cases']):
                    raise ValueError('Suite contains incomplete case results')
                item = SuiteAgentResult(entry['agent_id'], outcomes, len(entry['cases']))
                items.append(item)
                store.append({'event': 'agent_completed', 'agent_id': item.agent_id, 'item': agent_to_json(item)})
            result = BenchmarkSuiteResult(store.suite_id, tuple(j['agent_id'] for j in current['jobs']), tuple(items))
            store.append({'event': 'suite_completed', 'summary': suite_summary(result)})
        return self.result(suite)

    def evaluate_gt(self, suite, *, output=None, ask=None):
        from agentbench.harness.ground_truth.evaluator import evaluate_suite
        return evaluate_suite(suite, self.root, environ=self.environ,
                              output=output or (lambda _: None), ask=ask)

    @staticmethod
    def _validate_submission(response, request):
        from agentbench.sdk.integration.cases import case_bytes
        case_bytes(response)
        ids = {step['input']['input_id'] for step in request['steps']}
        issues, gaps = response['issues'], response['evidence_gaps']
        if any(not isinstance(issue, dict) or issue.get('input_id') not in ids
               or not isinstance(issue.get('message'), str) or not issue['message'].strip()
               for issue in issues):
            raise ValueError('Each external finding must cite an executed input_id and a message')
        if ((response['status'] == 'issue') != bool(issues)
                or response['status'] == 'pass' and gaps
                or response['status'] == 'inconclusive' and not gaps):
            raise ValueError('Judge status, findings and evidence gaps disagree')
