"""Execute imported Issue Cases through EvaluationService, then measure detection."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from filelock import FileLock

from agentbench.evaluation import EvaluationService
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.scheduling.retry import RetryPolicy
from agentbench.harness.ground_truth.detection import assess, oracle_model
from agentbench.harness.ground_truth.files import EVIDENCE_LIMIT, read_bytes, read_json, within
from agentbench.harness.ground_truth.issues import load_issue
from agentbench.harness.ground_truth.trajectories import read_candidate
from agentbench.observe.view_api import SuiteRunCatalogAPI
from agentbench.sdk.common.artifacts import Artifacts
from .exp1_inputs import load_cases
from .exp1_metrics import summarize

SCHEMA = 'abb.exp1.v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def token_usage(candidate):
    total = missing = 0
    for step in candidate.get('steps', []):
        if step['kind'] != 'model':
            continue
        usage = step['output'].get('usage') or {}
        tokens = usage.get('total_tokens')
        if tokens is None:
            first = usage.get('prompt_tokens', usage.get('input_tokens'))
            second = usage.get('completion_tokens', usage.get('output_tokens'))
            if type(first) is int and type(second) is int:
                tokens = first + second
        if type(tokens) is int and tokens >= 0:
            total += tokens
        else:
            missing += 1
    return {'known_tokens': total, 'missing_usage_calls': missing,
            'total_tokens': None if missing else total}


class Experiment1:
    def __init__(self, root, *, environ=None, execution_service=None, ask=None, output=print):
        self.engine = execution_service or EvaluationService(root, environ=environ)
        self.root = Path(root).resolve()
        self.environ = self.engine.environ
        self.ask = ask
        self.output = output

    def run(self, agent_id, case_dir, *, tests=50, workers=1, results_dir=None,
            prompt_template=None, scenario_file=None, model=None, timeout=2400):
        if type(workers) is not int or workers < 1:
            raise ValueError('--workers must be positive')
        if timeout <= 0:
            raise ValueError('--timeout must be positive')
        groups = load_cases(case_dir, tests)
        info = self.engine.agent(agent_id)
        references = {g['issue_id']: load_issue(self.root, agent_id, g['issue_id']) for g in groups}
        for reference in references.values():
            expected = reference['definition'].get('commit_version')
            actual = info['source'].get('revision')
            if expected and actual != expected:
                raise ValueError(f"{reference['issue_id']}: reference commit_version {expected} differs from "
                                 f'configured target revision {actual}; prepare the correct Agent version first')
        selected_oracle = oracle_model(self.environ)  # Fail before executing if the oracle is not configured.
        prompts = {}
        for key, path in [('template', prompt_template), ('scenario', scenario_file)]:
            if path is not None:
                prompts[key] = read_bytes(Path(path)).decode('utf-8-sig')
        experiment_id = 'exp1_' + uuid4().hex[:16]
        parent = Path(results_dir).resolve() if results_dir else Path(case_dir).resolve().parent / 'results'
        directory = parent / experiment_id
        directory.mkdir(parents=True, exist_ok=False)
        files = Artifacts(directory, environ=self.environ)
        plan = {'schema': SCHEMA, 'experiment_id': experiment_id, 'agent_id': agent_id,
                'created_at': datetime.now(timezone.utc).isoformat(), 'budget': tests, 'workers': workers,
                'target': info, 'target_model_override': model, 'max_target_retries': 0,
                'oracle': {'provider': 'openrouter', 'model': selected_oracle.model,
                           'endpoint': selected_oracle.base_url},
                'case_directory': str(Path(case_dir).resolve()), 'prompts': prompts,
                'prompt_sha256': fingerprint(prompts), 'issues': groups, 'execution_complete': False}
        # Only Cases and the public profile reach the native executor. References
        # and issue identity stay in this host-only experiment record.
        for issue_id, reference in references.items():
            files.save(f'{issue_id}/reference.json', reference)
        files.save('plan.json', plan)
        self.output(f'Exp1: {directory}; {len(groups)} Issues, budget {tests} each')
        started = time.monotonic()

        def execute(group):
            issue_id = group['issue_id']
            location = directory / issue_id
            record = {'state': 'running', 'suite': None}
            files.save(f'{issue_id}/execution.json', record)
            then = time.monotonic()
            try:
                result = self.engine.execute(agent_id, group['cases'], results_dir=location,
                    model=model, timeout=timeout,
                    max_steps=max(len(c['inputs']) for c in group['cases']),
                    concurrency=ConcurrencySettings(1), retry_policy=RetryPolicy(max_retries=0))
                record.update(state='finished', suite=result['directory'])
            except Exception as exc:
                record.update(state='failed', error=str(exc))
                # Preserve a failed Suite when execution raised after durable creation.
                suites = list((location / 'suites').glob('*/plan.json'))
                if len(suites) == 1:
                    record['suite'] = str(suites[0].parent)
            finally:
                record['wall_seconds'] = time.monotonic() - then
                files.save(f'{issue_id}/execution.json', record)
            return issue_id, record['state']

        with ThreadPoolExecutor(max_workers=min(workers, len(groups))) as pool:
            futures = [pool.submit(execute, group) for group in groups]
            for future in as_completed(futures):
                issue_id, state = future.result()
                self.output(f'Exp1: {issue_id} execution {state}')
        plan.update(execution_complete=True, execution_wall_seconds=time.monotonic() - started)
        files.save('plan.json', plan)
        return self.match(directory)

    def match(self, directory, *, retry_failed=False):
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise ValueError('Experiment directory does not exist')
        with FileLock(str(directory / '.exp1.lock'), timeout=0):
            return self._match(directory, retry_failed=retry_failed)

    def _match(self, directory, *, retry_failed):
        plan = read_json(directory / 'plan.json', limit=EVIDENCE_LIMIT)
        if plan.get('schema') != SCHEMA or not plan.get('execution_complete'):
            raise ValueError('Matching requires a completed exp1 execution plan')
        model = oracle_model(self.environ)
        files = Artifacts(directory, environ=self.environ)
        results = []
        started = time.monotonic()
        assessment_id = 'assessment_' + uuid4().hex[:16]
        for group in plan['issues']:
            issue_id = group['issue_id']
            location = within(directory, directory / issue_id)
            execution = read_json(location / 'execution.json')
            reference = read_json(location / 'reference.json', limit=EVIDENCE_LIMIT)
            catalog, attempts, case_errors, error = {}, {}, {}, None
            try:
                if not execution.get('suite'):
                    raise ValueError(execution.get('error') or 'No execution Suite was saved')
                suite = within(location, Path(execution['suite']))
                snapshot = self.engine.result(suite)['suite']
                if snapshot['state'] in ('running', 'queued'):
                    raise ValueError('Suite execution is not finished')
                catalog = SuiteRunCatalogAPI(suite / 'events.json').entries(snapshot=snapshot)
                for job in snapshot['jobs']:
                    if job['agent_id'] == plan['agent_id']:
                        attempts.update({c['case_index']: c.get('attempts') or [] for c in job['cases']})
                        case_errors.update({c['case_index']: c.get('error') or job.get('preparation_error')
                                            for c in job['cases']})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                error = str(exc)
            rows = []
            for index, case in enumerate(group['cases']):
                row = {'test_index': index + 1, 'case_id': case['case_id'], 'hit': None,
                       'execution_attempts': len(attempts.get(index, [])), 'reason': error or 'No saved execution'}
                rows.append(row)
                if error:
                    continue
                try:
                    matches = [(api, meta) for api, meta in catalog.values()
                               if meta.get('agent') == plan['agent_id'] and meta.get('case_index') == index
                               and meta.get('attempt_id')]
                    if len(matches) != 1 or len(attempts.get(index, [])) != 1:
                        detail = case_errors.get(index)
                        raise ValueError(f'Expected exactly one saved execution attempt for this Case; {detail or "no unambiguous trace"}')
                    api, meta = matches[0]
                    if meta.get('case_id') not in (None, case['case_id']):
                        raise ValueError('Saved Case identity differs from the frozen plan')
                    attempt = attempts[index][0]
                    result = attempt.get('result') or {}
                    states = (attempt, result, result.get('artifacts') or {})
                    if any(s.get('host_acceptance') == 'rejected' or
                           s.get('evidence_status') in ('missing', 'invalid', 'failed') for s in states):
                        raise ValueError('Execution evidence was rejected or is unavailable')
                    candidate = read_candidate(api, environ=self.environ)
                    row.update(run_id=meta['id'], trajectory_sha256=fingerprint(candidate),
                               target_usage=token_usage(candidate))
                    row.update(assess(reference, candidate, directory=location / 'oracle-calls',
                                      environ=self.environ, model=model, ask=self.ask, retry_failed=retry_failed))
                except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                    row.update(hit=None, reason=str(exc))
                self.output(f"Exp1: {issue_id} test {index + 1}: {row['hit']}")
            hits = [r['test_index'] for r in rows if r['hit'] is True]
            results.append({'issue_id': issue_id, 'suite': execution.get('suite'),
                            'submitted_tests': len(rows),
                            'execution_attempts': sum(r['execution_attempts'] for r in rows),
                            'hit_count': len(hits), 'first_hit': min(hits) if hits else None,
                            'execution_wall_seconds': execution.get('wall_seconds'),
                            'tests': rows})
            files.save(f'assessments/{assessment_id}.json', {'status': 'running', 'issues': results})
        metrics = summarize(results, plan['budget'])
        executed = sum(g['execution_attempts'] for g in results)
        usages = [t.get('target_usage', {}).get('total_tokens') for g in results for t in g['tests']]
        known = sum(t.get('target_usage', {}).get('known_tokens', 0) for g in results for t in g['tests'])
        total = sum(usages) if all(u is not None for u in usages) else None
        value = {'schema': SCHEMA, 'experiment_id': plan['experiment_id'], 'directory': str(directory),
                 'assessment_id': assessment_id, 'agent_id': plan['agent_id'], 'budget': plan['budget'],
                 'oracle': {'provider': 'openrouter', 'model': model.model, 'endpoint': model.base_url},
                 'status': 'partial' if any(t['hit'] is None for g in results for t in g['tests']) or
                           any(g['submitted_tests'] < plan['budget'] for g in results) else 'completed',
                 'issue_count': len(results), 'issues': results, 'metrics': metrics,
                 'execution_wall_seconds': plan.get('execution_wall_seconds'),
                 'matching_wall_seconds': time.monotonic() - started,
                 'cost': {'execution_attempts': executed,
                          'mean_execution_attempts_per_issue': executed / len(results),
                          'known_target_tokens': known, 'recorded_target_tokens': total,
                          'mean_recorded_target_tokens_per_issue': total / len(results) if total is not None else None,
                          'mean_execution_wall_seconds_per_issue': sum(g['execution_wall_seconds'] or 0 for g in results) / len(results),
                          'testing_agent_tokens': None, 'total_llm_tokens': None}}
        files.save(f'assessments/{assessment_id}.json', value)
        files.save('result.json', value)
        # Return the redacted representation just written to disk.
        return self.result(directory)

    @staticmethod
    def result(directory):
        value = read_json(Path(directory) / 'result.json', limit=EVIDENCE_LIMIT)
        if value.get('schema') != SCHEMA:
            raise ValueError('Not an exp1 result')
        return value
