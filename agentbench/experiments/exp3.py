"""Replay one GT reproduction against a frozen external repair source tree."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from agentbench.evaluation import EvaluationService
from agentbench.evaluation.modified_targets import prepare_modified_target
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.ground_truth.files import EVIDENCE_LIMIT, read_json
from agentbench.harness.ground_truth.issues import load_issue
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

    def gen_project(self, agent_id, *, issue, output, records_dir=None, no_run=False):
        return export_project(self.engine, self.root, agent_id, issue, output,
                              records_dir=records_dir, output_fn=self.output, no_run=no_run)

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
        parent = Path(results_dir).resolve() if results_dir else self.root.parent / 'r/exp3'
        if parent.is_relative_to(source) or parent.is_relative_to(self.root):
            raise ValueError('Save Exp3 results outside the submitted source and ABB repository')
        directory = parent / ('exp3_' + uuid4().hex[:16])
        directory.mkdir(parents=True, exist_ok=False)
        files = Artifacts(directory, environ=self.environ)
        value = {'schema': 'abb.exp3.v1', 'agent_id': agent_id, 'issue_number': issue,
                 'directory': str(directory), 'created_at': datetime.now(timezone.utc).isoformat(),
                 'requested_runs': runs, 'source': str(source), 'status': 'preparing',
                 'verdict': 'NOT_JUDGED', 'scope': 'original_reproduction_case',
                 'baseline': None, 'trials': [], 'target_model_override': model,
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
            # A fresh baseline proves this Case can expose the issue in the same
            # environment. It is additional to, not one of, the requested runs.
            value['baseline'] = self._trial(agent_id, case, base,
                directory / 'baseline', model, timeout)
            self.output(f'Exp3: baseline: {value["baseline"]["verdict"]}')
            files.save('result.json', value)
            for index in range(runs):
                self.output(f'Exp3: [{index + 1}/{runs}] starting independent repair execution')
                row = self._trial(agent_id, case, candidate,
                    directory / 'trials' / f'{index + 1:04d}', model, timeout)
                row['run_index'] = index + 1
                value['trials'].append(row)
                files.save('result.json', value)
                self.output(f'Exp3: [{index + 1}/{runs}] {row["verdict"]}; {row["reason"]}')
            value['status'] = 'completed'
        except BaseException as exc:
            value.update(status='failed' if isinstance(exc, Exception) else 'interrupted', error=str(exc))
            raise
        finally:
            value['wall_seconds'] = time.monotonic() - started
            value['completed_runs'] = len(value['trials'])
            value['reason'] = 'Execution evidence saved; run exp3 judge to assess the repair.'
            files.save('result.json', value)
        self.output(f'Exp3: {value["verdict"]}; results: {directory}')
        return self.result(directory)

    def _trial(self, agent_id, case, target, directory, model, timeout):
        files = Artifacts(directory, environ=self.environ)
        row = {'hit': None, 'label': None, 'verdict': 'NOT_JUDGED', 'suite': None,
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
            row.update(state='finished', reason='Execution evidence saved; not judged.')
        except BaseException as exc:
            row.update(state='failed' if isinstance(exc, Exception) else 'interrupted', reason=str(exc))
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
        value['judgments'] = [read_json(path, limit=EVIDENCE_LIMIT)
                              for path in sorted((Path(directory) / 'judgments').glob('*/result.json'))]
        return value
