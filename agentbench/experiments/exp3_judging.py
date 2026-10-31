"""Judge frozen Exp3 evidence without preparing or executing an Agent."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from agentbench.harness.ground_truth.detection import oracle_model
from agentbench.harness.ground_truth.files import EVIDENCE_LIMIT, read_json
from agentbench.harness.ground_truth.matching import validate_match
from agentbench.harness.ground_truth.repair import (
    REPAIR_SYSTEM, adapt_repair_reply, assess_repair, repair_payload,
    repair_trial_verdict, summarize, validate_repair_observation)
from agentbench.harness.ground_truth.trajectories import reference_step_id
from agentbench.sdk.common.artifacts import Artifacts
from .exp1 import fingerprint


def _absolute(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Use an absolute path')
    return path.resolve()


def _read(path):
    return read_json(path, limit=EVIDENCE_LIMIT)


def _unknown(reason):
    return dict(label='unknown', reason=reason, reference_step_ids=[], candidate_step_ids=[],
                candidate_decisive_step=None, candidate_observation=None)


class RepairJudging:
    def __init__(self, experiment):
        self.directory = _absolute(experiment)
        self.result = _read(self.directory / 'result.json')
        if self.result.get('schema') != 'abb.exp3.v1':
            raise ValueError('Not an Exp3 result')
        if self.result.get('status') in ('preparing', 'running'):
            raise ValueError('Wait until execution has stopped before judging')
        self.reference = _read(self.directory / 'reference.json')
        definition = _read(self.directory / 'definition.json')
        case = _read(self.directory / 'case.json')
        if any(definition.get(k) != v for k, v in self.reference['definition'].items()):
            raise ValueError('Frozen reference and definition disagree')
        if fingerprint(case) != self.result['case_sha256']:
            raise ValueError('Frozen Case hash mismatch')
        if self.reference['agent_id'] != self.result['agent_id']:
            raise ValueError('Frozen reference Agent mismatch')
        count = self.result['requested_runs']
        if type(count) is not int or count < 1 or len(self.result['trials']) > count:
            raise ValueError('Invalid execution count')
        self.rows = {}
        identities = {}
        for index in range(count + 1):
            key = 'baseline' if index == 0 else f'trials/{index:04d}'
            rows = self.result['trials']
            row = self.result.get('baseline') if index == 0 else rows[index - 1] if index <= len(rows) else None
            path = self.directory / key / 'trajectory.json'
            trajectory = _read(path) if path.exists() else None
            if trajectory is not None:
                if not row or fingerprint(trajectory) != row.get('trajectory_sha256'):
                    raise ValueError(f'{key}: trajectory hash mismatch')
                if trajectory.get('agent_id') != self.result['agent_id'] or trajectory.get('case_id') != case['case_id']:
                    raise ValueError(f'{key}: trajectory identity mismatch')
            self.rows[key] = (row or {}, trajectory)
            identities[key] = {'run_id': (row or {}).get('run_id'),
                               'execution_status': (row or {}).get('execution_status'),
                               'trajectory_sha256': fingerprint(trajectory) if trajectory is not None else None}
        self.manifest = {'experiment_id': self.directory.name,
                         'result_sha256': fingerprint(self.result),
                         'reference_sha256': fingerprint(self.reference),
                         'definition_sha256': fingerprint(definition),
                         'case_sha256': fingerprint(case), 'runs': identities}

    def export(self, output):
        directory = _absolute(output)
        directory.mkdir(parents=True, exist_ok=False)
        files = Artifacts(directory, environ={})
        entries = {}
        for key, (_, trajectory) in self.rows.items():
            files.save(f'{key}/trajectory.json', trajectory)
            if trajectory is not None:
                files.save(f'{key}/judge-input.json', repair_payload(self.reference, trajectory))
            entries[key] = _unknown('Replace with the evidence-based review and exact citations.')
        files.save('reference.json', self.reference)
        template = {'schema': 'abb.exp3.manual.v1', 'manifest': self.manifest,
                    'reviewer': '', 'decisions': entries}
        files.save('review.json', template)
        (directory / 'instructions.txt').write_text(
            REPAIR_SYSTEM + '\n\nFill reviewer and every decision in review.json. '
            'Do not edit the manifest. Import validates identity and citations, not the '
            'semantic correctness of human reasoning. Missing evidence must remain unknown.\n', encoding='utf-8')
        return {'directory': str(directory), 'review': str(directory / 'review.json')}

    def _validate(self, key, reply):
        row, trajectory = self.rows[key]
        reply = adapt_repair_reply(reply)
        references = {reference_step_id(t['attempt'], s['step_id'])
                      for t in self.reference['trajectories'] for s in t['steps']}
        if trajectory is None or trajectory.get('status') == 'failed' or not trajectory.get('steps'):
            if reply['label'] != 'unknown':
                raise ValueError(f'{key}: no usable execution evidence; decision must be unknown')
        reply = validate_match(reply, references, {s['step_id'] for s in (trajectory or {}).get('steps', [])})
        validate_repair_observation(reply, trajectory)
        label = reply['label']
        verdict = repair_trial_verdict(label, row.get('execution_status'))
        if key == 'baseline':
            verdict = {'bug_exist': 'REPRODUCED', 'bug_fixed': 'NOT_REPRODUCED', 'unknown': 'UNKNOWN'}[label]
        return {**reply, 'hit': reply['match'], 'verdict': verdict,
                **self.manifest['runs'][key]}

    def _save(self, directory, source, decisions, **metadata):
        baseline = decisions['baseline']
        trials = [v for k, v in decisions.items() if k != 'baseline']
        value = {'schema': 'abb.exp3.judgment.v1', 'judgment_id': directory.name,
                 'directory': str(directory), 'created_at': datetime.now(timezone.utc).isoformat(),
                 'source': source, 'manifest': self.manifest, 'decisions': decisions,
                 'verdict': summarize(baseline, trials, self.result['requested_runs']), **metadata}
        Artifacts(directory, environ={}).save('result.json', value)
        return value

    def _new_directory(self):
        directory = self.directory / 'judgments' / uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def import_review(self, path):
        review = _read(_absolute(path))
        if review.get('schema') != 'abb.exp3.manual.v1' or review.get('manifest') != self.manifest:
            raise ValueError('Manual review does not match this frozen experiment and its evidence')
        reviewer = review.get('reviewer')
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError('Manual review requires a reviewer')
        if not isinstance(review.get('decisions'), dict) or set(review['decisions']) != set(self.rows):
            raise ValueError('Review must contain exactly one decision per baseline and requested trial')
        decisions = {key: self._validate(key, review['decisions'][key]) for key in self.rows}
        directory = self._new_directory()
        Artifacts(directory, environ={}).save('review.json', review)
        return self._save(directory, 'manual', decisions, reviewer=reviewer)

    def auto(self, *, environ, model=None, ask=None):
        selected = oracle_model(environ)
        if model:
            selected = replace(selected, model=model)
        directory = self._new_directory()
        started = time.monotonic()
        decisions = {}
        for key, (_, trajectory) in self.rows.items():
            try:
                if trajectory is None:
                    raise ValueError('No saved trajectory')
                assessment = assess_repair(self.reference, trajectory,
                    directory=directory / key / 'oracle', environ=environ, model=selected, ask=ask)
                reply = {k: v for k, v in assessment['match'].items() if k != 'match'}
                decisions[key] = {**self._validate(key, reply), 'assessment': assessment}
            except (OSError, ValueError, RuntimeError) as exc:
                from agentbench.observe.store import environment_secrets, redact
                reason = redact(str(exc), environment_secrets(environ))
                decisions[key] = {**self._validate(key, _unknown(reason)), 'error': reason}
        return self._save(directory, 'auto', decisions, model=selected.model,
                          endpoint=selected.base_url, protocol='abb.repair-judge.v2',
                          wall_seconds=time.monotonic() - started)
