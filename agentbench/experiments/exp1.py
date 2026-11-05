"""Execute ordered Issue Cases through EvaluationService and a hidden oracle."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
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
from .exp1_metrics import aggregate, summarize, summarize_rounds

SCHEMA = 'abb.exp1.v2'
LEGACY_SCHEMA = 'abb.exp1.v1'


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


def execution_row(run, index, case):
    return {'test_index': index + 1, 'case_id': case['case_id'], 'hit': None,
            'suite': run.get('suite'), 'execution_state': run['state'],
            'execution_status': run.get('execution_status'),
            'execution_wall_seconds': run.get('wall_seconds'),
            'execution_attempts': 0, 'reason': 'No saved assessment'}


class Experiment1:
    def __init__(self, root, *, environ=None, execution_service=None, ask=None, output=print):
        self.engine = execution_service or EvaluationService(root, environ=environ)
        self.root = Path(root).resolve()
        self.environ = self.engine.environ
        self.ask = ask
        self.output = output

    def run(self, agent_id, cases_file, *, issue, results_dir=None,
            prompt_template=None, scenario_file=None, model=None, timeout=2400):
        if type(issue) is not int or issue < 1:
            raise ValueError('--issue must be a positive integer')
        if timeout <= 0:
            raise ValueError('--timeout must be positive')
        cases = load_cases(cases_file)
        issue_id = f'issue_{issue}'
        reference = load_issue(self.root, agent_id, issue_id)
        revision = reference['definition'].get('commit_version')
        if not isinstance(revision, str) or not re.fullmatch('[0-9a-fA-F]{40}', revision):
            raise ValueError('Issue commit_version must be a full 40-character commit SHA')
        prompts = {}
        for key, path in [('template', prompt_template), ('scenario', scenario_file)]:
            if path is not None:
                prompts[key] = read_bytes(Path(path)).decode('utf-8-sig')
        selected_oracle = oracle_model(self.environ)
        preparing = time.monotonic()
        target = self.engine.prepare(agent_id, revision, output=self.output)
        if target.revision.lower() != revision.lower():
            raise ValueError('Prepared target revision differs from Issue commit_version')
        info = self.engine.agent(agent_id, target=target)
        preparation_seconds = time.monotonic() - preparing
        experiment_id = 'exp1_' + uuid4().hex[:16]
        parent = Path(results_dir).resolve() if results_dir else Path(cases_file).resolve().parent / 'results'
        directory = parent / experiment_id
        directory.mkdir(parents=True, exist_ok=False)
        files = Artifacts(directory, environ=self.environ)
        group = {'issue_id': issue_id, 'issue_number': issue, 'available_cases': len(cases), 'cases': cases}
        plan = {'schema': SCHEMA, 'experiment_id': experiment_id, 'agent_id': agent_id,
                'created_at': datetime.now(timezone.utc).isoformat(), 'budget': len(cases),
                'execution_mode': 'ordered_cases', 'target': info,
                'prepared_targets': {issue_id: target.describe()}, 'stop_on_hit': True,
                'preparation_wall_seconds': preparation_seconds,
                'target_model_override': model, 'max_target_retries': 0,
                'oracle': {'provider': 'openrouter', 'model': selected_oracle.model,
                           'endpoint': selected_oracle.base_url},
                'case_file': str(Path(cases_file).resolve()), 'cases_sha256': fingerprint(cases),
                'prompts': prompts, 'prompt_sha256': fingerprint(prompts),
                'issues': [group], 'execution_complete': False}
        # Issue identity and reference definitions remain host-only.
        files.save(f'{issue_id}/reference.json', reference)
        files.save('plan.json', plan)
        self.output(f'Exp1: {directory}; {agent_id} {issue_id}; commit {target.revision}; {len(cases)} Cases')
        record = {'state': 'running', 'repetitions': [], 'stop_reason': None}
        files.save(f'{issue_id}/execution.json', record)
        rows = []
        assessment_id = 'assessment_' + uuid4().hex[:16]
        with FileLock(str(directory / '.exp1.lock'), timeout=0):
            try:
                for index, case in enumerate(cases):
                    run = {'test_index': index + 1, 'source_case_index': index,
                           'case_id': case['case_id'], 'state': 'running', 'suite': None}
                    record['repetitions'].append(run)
                    files.save(f'{issue_id}/execution.json', record)
                    self._execute_case(plan, group, case, run, record, files, target, model, timeout)
                    row = self._assess_case(plan, group, run, index, reference, directory, selected_oracle)
                    rows.append(row)
                    files.save(f'{issue_id}/repetitions/{index + 1:04d}/assessment.json', row)
                    self._publish(directory, plan, [(group, record, rows)], assessment_id)
                    verdict = 'unknown' if row['hit'] is None else int(row['hit'])
                    self.output(f'Exp1: [{index + 1}/{len(cases)}] {case["case_id"]}: {verdict}')
                    if row['hit'] is True:
                        record['stop_reason'] = 'hit'
                        break
                record.update(state='finished', stop_reason=record['stop_reason'] or 'budget_exhausted')
                plan['execution_complete'] = True
            finally:
                if record['state'] == 'running':
                    record['state'] = 'interrupted'
                    record['stop_reason'] = 'interrupted'
                # Preserve an interrupted Case without turning absent evidence into a negative.
                for index in range(len(rows), len(record['repetitions'])):
                    rows.append(execution_row(record['repetitions'][index], index, cases[index]))
                record['wall_seconds'] = sum(r.get('wall_seconds', 0) for r in record['repetitions'])
                plan['execution_wall_seconds'] = record['wall_seconds']
                files.save(f'{issue_id}/execution.json', record)
                files.save('plan.json', plan)
                value = self._publish(directory, plan, [(group, record, rows)], assessment_id)
        self.output(f'Exp1: result={value["score"]}; first_hit={value["first_hit"]}')
        if value['matched_case_path']:
            self.output(f'Exp1: matched Case: {value["matched_case_path"]}')
        return value

    def _execute_case(self, plan, group, case, run, record, files, target, model, timeout):
        relative = f'{group["issue_id"]}/repetitions/{run["test_index"]:04d}'
        location = files.directory / relative
        started = time.monotonic()
        try:
            result = self.engine.execute(plan['agent_id'], [deepcopy(case)], results_dir=location,
                target=target, model=model, timeout=timeout, max_steps=len(case['inputs']),
                concurrency=ConcurrencySettings(1), retry_policy=RetryPolicy(max_retries=0))
            run.update(state='finished', suite=result['directory'],
                       execution_status=result['suite']['summary']['execution_status'])
        except BaseException as exc:
            run.update(state='failed' if isinstance(exc, Exception) else 'interrupted',
                       execution_status='failed', error=str(exc))
            suites = list((location / 'suites').glob('*/plan.json'))
            if len(suites) == 1:
                run['suite'] = str(suites[0].parent)
            if not isinstance(exc, Exception):
                raise
        finally:
            run['wall_seconds'] = time.monotonic() - started
            files.save(f'{relative}/execution.json', run)
            files.save(f'{group["issue_id"]}/execution.json', record)

    def _assess_case(self, plan, group, run, index, reference, directory, model, *, retry_failed=False):
        separate_suites = plan.get('execution_mode') in ('ordered_cases', 'repeat_case', 'case_rounds')
        case = group['cases'][run.get('source_case_index', 0) if separate_suites else index]
        case_index = 0 if separate_suites else index
        row = execution_row(run, index, case)
        if plan['schema'] == LEGACY_SCHEMA:
            row['round_index'] = run.get('round_index', index + 1)
        location = within(directory, directory / group['issue_id'])
        started = time.monotonic()
        try:
            if not run.get('suite'):
                raise ValueError(run.get('error') or 'No execution Suite was saved')
            suite = within(location, Path(run['suite']))
            snapshot = self.engine.result(suite)['suite']
            if snapshot['state'] in ('running', 'queued'):
                raise ValueError('Suite execution is not finished')
            row['execution_status'] = snapshot['summary']['execution_status']
            attempts, case_errors = {}, {}
            for job in snapshot['jobs']:
                if job['agent_id'] == plan['agent_id']:
                    attempts.update({c['case_index']: c.get('attempts') or [] for c in job['cases']})
                    case_errors.update({c['case_index']: c.get('error') or job.get('preparation_error')
                                        for c in job['cases']})
            row['execution_attempts'] = len(attempts.get(case_index, []))
            catalog = SuiteRunCatalogAPI(suite / 'events.json').entries(snapshot=snapshot)
            matches = [(api, meta) for api, meta in catalog.values()
                       if meta.get('agent') == plan['agent_id'] and meta.get('case_index') == case_index
                       and meta.get('attempt_id')]
            if len(matches) != 1 or len(attempts.get(case_index, [])) != 1:
                detail = case_errors.get(case_index) or 'no unambiguous trace'
                raise ValueError(f'Expected exactly one saved execution attempt for this Case; {detail}')
            api, meta = matches[0]
            if meta.get('case_id') not in (None, case['case_id']):
                raise ValueError('Saved Case identity differs from the frozen plan')
            attempt = attempts[case_index][0]
            result = attempt.get('result') or {}
            states = (attempt, result, result.get('artifacts') or {})
            if any(s.get('host_acceptance') == 'rejected' or
                   s.get('evidence_status') in ('missing', 'invalid', 'failed') for s in states):
                raise ValueError('Execution evidence was rejected or is unavailable')
            candidate = read_candidate(api, environ=self.environ)
            row.update(run_id=meta['id'], trajectory_sha256=fingerprint(candidate), target_usage=token_usage(candidate))
            calls = (location / 'repetitions' / f'{index + 1:04d}' / 'oracle-calls'
                     if separate_suites else location / 'oracle-calls')
            row.update(assess(reference, candidate, directory=calls, environ=self.environ,
                              model=model, ask=self.ask, retry_failed=retry_failed))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            row.update(hit=None, reason=str(exc))
        finally:
            row['matching_wall_seconds'] = time.monotonic() - started
        return row

    def match(self, directory, *, retry_failed=False):
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise ValueError('Experiment directory does not exist')
        with FileLock(str(directory / '.exp1.lock'), timeout=0):
            plan = read_json(directory / 'plan.json', limit=EVIDENCE_LIMIT)
            if plan.get('schema') not in (SCHEMA, LEGACY_SCHEMA):
                raise ValueError('Not an exp1 execution plan')
            if plan['schema'] == LEGACY_SCHEMA and not plan.get('execution_complete'):
                raise ValueError('Legacy matching requires a completed execution plan')
            model = oracle_model(self.environ)
            if plan['schema'] == SCHEMA and (plan['oracle']['model'] != model.model or
                                            plan['oracle']['endpoint'] != model.base_url):
                raise ValueError('Oracle model and endpoint must match the frozen experiment')
            if plan['schema'] == LEGACY_SCHEMA:
                plan = {**plan, 'oracle': {'provider': 'openrouter', 'model': model.model,
                                         'endpoint': model.base_url}}
            results = []
            assessment_id = 'assessment_' + uuid4().hex[:16]
            for group in plan['issues']:
                location = within(directory, directory / group['issue_id'])
                execution = read_json(location / 'execution.json', limit=EVIDENCE_LIMIT)
                reference = read_json(location / 'reference.json', limit=EVIDENCE_LIMIT)
                separate = plan.get('execution_mode') in ('ordered_cases', 'repeat_case', 'case_rounds')
                runs = execution['repetitions'] if separate else [execution] * len(group['cases'])
                rows = []
                for index, run in enumerate(runs):
                    rows.append(self._assess_case(plan, group, run, index, reference, directory,
                                                 model, retry_failed=retry_failed))
                    self.output(f'Exp1: {group["issue_id"]} test {index + 1}: {rows[-1]["hit"]}')
                results.append((group, execution, rows))
            return self._publish(directory, plan, results, assessment_id)

    def _publish(self, directory, plan, results, assessment_id):
        files = Artifacts(directory, environ=self.environ)
        ordered = plan['schema'] == SCHEMA
        issues = []
        for group, execution, rows in results:
            rounds = summarize_rounds(rows) if not ordered else []
            scoring = rows if ordered else rounds
            hits = [r['test_index'] if ordered else r['round_index'] for r in scoring if r['hit'] is True]
            score = (1 if hits else 0 if len(scoring) >= plan['budget'] and
                     all(r['hit'] is False for r in scoring) else None)
            entry = {'issue_id': group['issue_id'], 'suite': execution.get('suite'),
                     'suites': [r.get('suite') for r in rows], 'submitted_tests': len(rows),
                     'execution_attempts': sum(r['execution_attempts'] for r in rows),
                     'hit_count': len(hits), 'first_hit': min(hits) if hits else None,
                     'execution_wall_seconds': (sum(r['execution_wall_seconds'] or 0 for r in rows)
                                                if ordered else execution.get('wall_seconds') or 0), 'tests': rows}
            if ordered:
                entry.update(score=score, budget=plan['budget'], stop_reason=execution.get('stop_reason'),
                             unexecuted_case_ids=[c['case_id'] for c in group['cases'][len(rows):]])
            else:
                entry.update(rounds=rounds, submitted_rounds=len(rounds))
            issues.append(entry)
        metrics = summarize([{'tests': g['tests'] if ordered else g['rounds']} for g in issues], plan['budget'])
        rows = [t for g in issues for t in g['tests']]
        usages = [r.get('target_usage', {}).get('total_tokens') for r in rows]
        known = sum(r.get('target_usage', {}).get('known_tokens', 0) for r in rows)
        total = sum(usages) if all(u is not None for u in usages) else None
        executed = sum(g['execution_attempts'] for g in issues)
        incomplete = any(t['hit'] is None for t in rows)
        if ordered:
            incomplete |= not plan.get('execution_complete') or any(g['score'] is None for g in issues)
        else:
            incomplete |= any(g['submitted_rounds'] < plan['budget'] for g in issues)
        value = {'schema': plan['schema'], 'experiment_id': plan['experiment_id'], 'directory': str(directory),
                 'assessment_id': assessment_id, 'agent_id': plan['agent_id'], 'budget': plan['budget'],
                 'oracle': plan['oracle'], 'status': 'partial' if incomplete else 'completed',
                 'issue_count': len(issues), 'issues': issues, 'metrics': metrics,
                 'execution_wall_seconds': (sum(g['execution_wall_seconds'] for g in issues)
                                            if ordered else plan.get('execution_wall_seconds')),
                 'matching_wall_seconds': sum(r.get('matching_wall_seconds', 0) for r in rows),
                 'cost': {'execution_attempts': executed, 'mean_execution_attempts_per_issue': executed / len(issues),
                          'known_target_tokens': known, 'recorded_target_tokens': total,
                          'mean_recorded_target_tokens_per_issue': total / len(issues) if total is not None else None,
                          'mean_execution_wall_seconds_per_issue': sum(g['execution_wall_seconds'] for g in issues) / len(issues),
                          'testing_agent_tokens': None, 'total_llm_tokens': None}}
        if ordered:
            first_hit = issues[0]['first_hit']
            matched = plan['issues'][0]['cases'][first_hit - 1] if first_hit else None
            matched_path = f'assessments/{assessment_id}/matched-case.json' if matched else None
            if matched_path:
                files.save(matched_path, matched)
            value.update(metrics_unit='case_executions', score=issues[0]['score'], first_hit=first_hit,
                         matched_case=matched, matched_case_path=str(directory / matched_path) if matched_path else None,
                         prepared_targets=plan['prepared_targets'],
                         preparation_wall_seconds=plan['preparation_wall_seconds'])
        files.save(f'assessments/{assessment_id}.json', value)
        files.save('result.json', value)
        return self.result(directory)

    @staticmethod
    def result(directory):
        if isinstance(directory, (list, tuple)):
            values = [Experiment1.result(path) for path in directory]
            if not values:
                raise ValueError('Supply at least one experiment')
            return values[0] if len(values) == 1 else aggregate(values)
        value = read_json(Path(directory) / 'result.json', limit=EVIDENCE_LIMIT)
        if value.get('schema') not in (SCHEMA, LEGACY_SCHEMA):
            raise ValueError('Not an exp1 result')
        return value
