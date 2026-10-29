"""Replay one GT reproduction against a frozen external repair source tree."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from agentbench.evaluation import EvaluationService
from agentbench.evaluation.modified_targets import prepare_modified_target
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.ground_truth.detection import oracle_model
from agentbench.harness.ground_truth.files import EVIDENCE_LIMIT, read_json
from agentbench.harness.ground_truth.issues import load_issue
from agentbench.harness.ground_truth.repair import assess_defect, assess_expected, summarize, trial_verdict
from agentbench.harness.ground_truth.repair_requirements import prepare_requirements
from agentbench.harness.scheduling.retry import RetryPolicy
from agentbench.sdk.common.artifacts import Artifacts
from .exp1 import fingerprint, token_usage
from .exp3_projects import definition, export_project, reproduction_case


class Experiment3:
    def __init__(self, root, *, environ=None, execution_service=None, ask=None, output=print):
        self.root = Path(root).resolve()
        self.engine = execution_service or EvaluationService(root, environ=environ)
        self.environ = self.engine.environ
        self.ask, self.output = ask, output

    def gen_project(self, agent_id, *, issue, output, records_dir=None):
        return export_project(self.engine, self.root, agent_id, issue, output,
                              records_dir=records_dir, output_fn=self.output)

    def run(self, agent_id, *, issue, source, runs=3, results_dir=None, model=None, timeout=2400):
        if type(runs) is not int or runs < 1:
            raise ValueError('--runs must be a positive integer')
        if timeout <= 0:
            raise ValueError('--timeout must be positive')
        source = Path(source)
        if not source.is_absolute() or not source.is_dir():
            raise ValueError('--source must be an absolute path to a source directory')
        source = source.resolve()
        document = definition(self.root, agent_id, issue)
        reference = load_issue(self.root, agent_id, f'issue_{issue}')
        if any(document.get(key) != item for key, item in reference['definition'].items()):
            raise ValueError('GT definition changed while preparing the run; retry with stable GT')
        case = reproduction_case(document)
        selected_oracle = oracle_model(self.environ)
        parent = Path(results_dir).resolve() if results_dir else self.root.parent / 'r/exp3'
        if parent.is_relative_to(source) or parent.is_relative_to(self.root):
            raise ValueError('Save Exp3 results outside the submitted source and ABB repository')
        directory = parent / ('exp3_' + uuid4().hex[:16])
        directory.mkdir(parents=True, exist_ok=False)
        files = Artifacts(directory, environ=self.environ)
        value = {'schema': 'abb.exp3.v1', 'agent_id': agent_id, 'issue_number': issue,
                 'directory': str(directory), 'created_at': datetime.now(timezone.utc).isoformat(),
                 'requested_runs': runs, 'source': str(source), 'status': 'preparing',
                 'verdict': 'UNKNOWN', 'scope': 'original_reproduction_case',
                 'baseline': None, 'trials': [], 'target_model_override': model,
                 'oracle': {'model': selected_oracle.model, 'endpoint': selected_oracle.base_url},
                 'case_sha256': fingerprint(case), 'max_target_retries': 0}
        files.save('case.json', case)
        files.save('reference.json', reference)
        files.save('definition.json', document)
        files.save('result.json', value)
        self.output(f'Exp3: result directory: {directory}')
        started = time.monotonic()
        try:
            base = self.engine.prepare(agent_id, document['commit_version'], output=self.output)
            if base.revision.lower() != document['commit_version'].lower():
                raise ValueError('Prepared target revision differs from Issue commit_version')
            candidate = prepare_modified_target(base, source, directory / 'target')
            value.update(base_target=base.describe(), candidate_target=candidate.describe(),
                         preparation_wall_seconds=time.monotonic() - started, status='running')
            files.save('plan.json', deepcopy(value))
            files.save('result.json', value)
            self.output(f'Exp3: {agent_id} issue_{issue}; base {base.revision}; {runs} repair validations')
            requirements = None
            try:
                requirements = prepare_requirements(document['expected'], case,
                    directory=directory / 'oracle', environ=self.environ, model=selected_oracle, ask=self.ask)
                value['expected_requirements'] = requirements
            except Exception as exc:
                value['expected_requirements_error'] = str(exc)
                self.output('Exp3: expected-behavior requirements unavailable; PASS cannot be established')
            files.save('result.json', value)
            # A fresh baseline proves this Case can expose the issue in the same
            # environment. It is additional to, not one of, the requested runs.
            value['baseline'] = self._trial(agent_id, case, reference, base,
                directory / 'baseline', selected_oracle, model, timeout, baseline=True)
            self.output(f'Exp3: baseline: {value["baseline"]["verdict"]}')
            files.save('result.json', value)
            for index in range(runs):
                self.output(f'Exp3: [{index + 1}/{runs}] starting independent repair execution')
                row = self._trial(agent_id, case, reference, candidate,
                    directory / 'trials' / f'{index + 1:04d}', selected_oracle, model, timeout,
                    requirements=requirements)
                row['run_index'] = index + 1
                value['trials'].append(row)
                value['verdict'] = summarize(value['baseline'], value['trials'], runs)
                files.save('result.json', value)
                self.output(f'Exp3: [{index + 1}/{runs}] {row["verdict"]}; {row["reason"]}')
            value['status'] = 'completed'
        except BaseException as exc:
            value.update(status='failed' if isinstance(exc, Exception) else 'interrupted', error=str(exc))
            raise
        finally:
            value['verdict'] = summarize(value['baseline'], value['trials'], runs)
            value['wall_seconds'] = time.monotonic() - started
            value['completed_runs'] = len(value['trials'])
            value['failure_reproduced_runs'] = sum(row['hit'] is True for row in value['trials'])
            value['reason'] = ('At least one repair run failed the original Case.' if value['verdict'] == 'FAIL'
                else 'All runs achieved the original Case expectation without the reported failure.'
                if value['verdict'] == 'PASS' else 'Baseline reproduction or repair evidence is unresolved.')
            files.save('result.json', value)
        self.output(f'Exp3: {value["verdict"]}; results: {directory}')
        return self.result(directory)

    def _trial(self, agent_id, case, reference, target, directory, oracle, model, timeout, *,
               baseline=False, requirements=None):
        files = Artifacts(directory, environ=self.environ)
        row = {'hit': None, 'expected_met': None, 'verdict': 'UNKNOWN', 'suite': None,
               'reason': 'Execution has not finished', 'state': 'running'}
        files.save('trial.json', row)
        started = time.monotonic()
        try:
            result = self.engine.execute(agent_id, [deepcopy(case)], target=target,
                results_dir=directory, model=model, timeout=timeout, max_steps=len(case['inputs']),
                concurrency=ConcurrencySettings(1), retry_policy=RetryPolicy(max_retries=0))
            row.update(suite=result['directory'], execution_status=result['suite']['summary']['execution_status'],
                       execution_wall_seconds=time.monotonic() - started)
            files.save('trial.json', row)
            trajectory, run_id = self._evidence(result, agent_id, case['case_id'])
            row.update(run_id=run_id, trajectory_sha256=fingerprint(trajectory),
                       target_usage=token_usage(trajectory))
            files.save('trajectory.json', trajectory)
            kwargs = {'environ': self.environ, 'model': oracle, 'ask': self.ask}
            detected = assess_defect(reference, trajectory, directory=directory / 'oracle/defect', **kwargs)
            row.update(hit=detected['hit'], defect_assessment=detected, reason=detected['reason'])
            files.save('trial.json', row)
            if not baseline and row['hit'] is False:
                if requirements is None:
                    row['reason'] = 'Expected-behavior requirements unavailable; repair cannot be confirmed'
                elif row['execution_status'] == 'completed':
                    expected = assess_expected(reference, trajectory,
                        requirements=requirements, directory=directory / 'oracle/expected', **kwargs)
                    row.update(expected_met=expected['hit'], expected_assessment=expected,
                               reason=expected['reason'])
                else:
                    row['reason'] = 'Execution did not complete; defect absence cannot prove repair'
            row.update(state='finished', verdict=trial_verdict(row['hit'], row['expected_met']))
            if baseline:
                row['verdict'] = ('REPRODUCED' if row['hit'] is True else
                                  'NOT_REPRODUCED' if row['hit'] is False else 'UNKNOWN')
        except BaseException as exc:
            row.update(state='failed' if isinstance(exc, Exception) else 'interrupted', reason=str(exc),
                       verdict=trial_verdict(row['hit'], row['expected_met']))
            if not isinstance(exc, Exception):
                raise
        finally:
            row['wall_seconds'] = time.monotonic() - started
            files.save('trial.json', row)
        return row

    def _evidence(self, result, agent_id, case_id):
        snapshot = result['suite']
        attempts = [a for job in snapshot['jobs'] if job['agent_id'] == agent_id
                    for c in job['cases'] if c['case_index'] == 0 for a in c.get('attempts') or []]
        runs = [r for r in result['runs'] if r.get('agent') == agent_id and r.get('case_index') == 0]
        if snapshot['state'] in ('running', 'queued') or len(attempts) != 1 or len(runs) != 1:
            errors = [c.get('error') or job.get('preparation_error')
                      for job in snapshot['jobs'] for c in job.get('cases', [])]
            detail = next((error for error in errors if error), 'no unambiguous retained run')
            raise ValueError(f'Expected one finished execution with usable evidence: {detail}')
        if runs[0].get('case_id') != case_id:
            raise ValueError('Execution Case identity differs from the frozen reproduction Case')
        attempt = attempts[0]
        outcome = attempt.get('result') or {}
        if any(s.get('host_acceptance') == 'rejected' or s.get('evidence_status') in ('missing', 'invalid', 'failed')
               for s in (attempt, outcome, outcome.get('artifacts') or {})):
            raise ValueError('Execution evidence was rejected or is unavailable')
        evidence = self.engine.evidence(result['directory'], runs[0]['id'])
        return evidence['trajectory'], runs[0]['id']

    @staticmethod
    def result(directory):
        value = read_json(Path(directory) / 'result.json', limit=EVIDENCE_LIMIT)
        if value.get('schema') != 'abb.exp3.v1':
            raise ValueError('Not an Exp3 result')
        return value
