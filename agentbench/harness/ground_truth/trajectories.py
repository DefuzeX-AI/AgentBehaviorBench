"""Reference and candidate trajectories for step-level GT comparison.

Both sides are abb.agent-trajectory.v1 documents. References must already be
saved beside their attempt; candidates are derived on read when a historical
package has none. Rendering never drops model inputs: an oversized comparison
stays pending instead of silently losing the evidence the matcher needs.
"""
import json
from pathlib import Path

from agentbench import trajectory
from agentbench.trajectory.render import render
from .files import within


def read_candidate(api, *, environ=None):
    value = trajectory.load(api.directory, environ=environ)
    if value.get('status') == 'failed':
        raise ValueError('Candidate trajectory derivation failed: ' + str(value.get('error')))
    return value


def read_reference(defect):
    """Saved reference trajectories only; GT preparation must have written them."""
    root = Path(defect['_case_directory'])
    values = []
    for attempt in defect['reference_attempts']:
        directory = within(root, root / 'attempts' / attempt)
        value = trajectory.read(directory)
        if value is None:
            raise ValueError(f'Reference attempt {attempt} has no trajectory.json; '
                             'run `agentbench trajectory build DIR --write`')
        if value.get('status') == 'failed':
            raise ValueError(f'Reference attempt {attempt} trajectory failed to derive')
        values.append({'attempt': attempt, **value})
    return values


def reference_step_id(attempt, step_id):
    return f'{attempt}/{step_id}'


def _metadata(value):
    metadata = value.get('metadata') or {}
    configuration = metadata.get('agent_configuration') or {}
    return {'task_instruction': metadata.get('task_instruction'),
            'agents': configuration.get('agents'),
            'tools': [t.get('name') or (t.get('function') or {}).get('name') for t in configuration.get('tools') or []
                      if isinstance(t, dict)],
            'framework': (metadata.get('system_architecture') or {}).get('framework'),
            'source_revision': (metadata.get('system_architecture') or {}).get('source_revision')}


def _summary(value):
    return {'status': value.get('status'), 'coverage': value.get('coverage'),
            'derived_on_read': bool(value.get('derived_on_read')), 'warnings': value.get('warnings')}


def matcher_payload(reference, candidate, defect, finding_summary, *, limit):
    """The second-stage request; both trajectories rendered in the same mode."""
    base = {'reference': {key: defect.get(key) for key in
                          ('summary', 'explanation', 'expected_behavior', 'observed_behavior', 'decisive_step')},
            'finding_summary': finding_summary}
    base['reference']['decisive_step'] = {**defect['decisive_step'],
        'step_ref': reference_step_id(defect['decisive_step']['attempt'], defect['decisive_step']['step_id'])}
    for mode in ('full', 'truncate_middle'):
        payload = {**base, 'render_mode': mode,
                   'reference_trajectories': [{
                       'attempt': item['attempt'], 'metadata': _metadata(item), **_summary(item),
                       'step_refs': [reference_step_id(item['attempt'], s['step_id']) for s in item['steps']],
                       'rendered': render(item, mode)} for item in reference],
                   'candidate_trajectory': {'metadata': _metadata(candidate), **_summary(candidate),
                                            'step_ids': [s['step_id'] for s in candidate['steps']],
                                            'rendered': render(candidate, mode)}}
        if len(json.dumps(payload, ensure_ascii=False).encode()) <= limit:
            return payload, mode
    raise ValueError('Matcher context too large even with truncated requests; decision remains pending')


def cited_steps(trajectories, refs):
    """The step records a decision cited, for the saved evidence row."""
    found = []
    for item in trajectories:
        attempt = item.get('attempt')
        for step in item['steps']:
            key = reference_step_id(attempt, step['step_id']) if attempt is not None else step['step_id']
            if key in refs:
                found.append({'attempt': attempt, 'step_id': step['step_id'], 'agent_name': step['agent_name'],
                              'kind': step['kind'], 'output': step.get('output'), 'tool_logs': step.get('tool_logs')})
    return found


def judge_cited_steps(finding):
    """Step ids a Judge finding names, when its report format carries them."""
    if not isinstance(finding, dict):
        return None
    for key in ('step_ids', 'steps', 'trajectory_steps'):
        value = finding.get(key)
        if isinstance(value, list) and value and all(type(v) is int for v in value):
            return value
    evidence = finding.get('evidence')
    if isinstance(evidence, dict) and isinstance(evidence.get('step_ids'), list):
        return [v for v in evidence['step_ids'] if type(v) is int] or None
    return None
