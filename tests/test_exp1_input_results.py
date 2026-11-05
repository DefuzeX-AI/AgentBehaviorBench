"""Final framework outputs are evidence without being model/tool steps."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.ground_truth import detection
from tests.test_exp1 import (prepared, project, oracle, inprocess_worker_permissions,
                            answer, case, collection, experiment)


OUTPUT = 'Simulator final output: invalid state reached.'


def candidate_trace():
    return {'agent_id': 'example', 'case_id': 'case', 'status': 'complete',
            'inputs': [{'ordinal': '0001', 'input_id': 'task', 'prompt': 'Run simulation',
                        'result': {'status': 'completed', 'output': OUTPUT}}],
            'steps': [{'step_id': n, 'agent_name': 'example', 'kind': 'model',
                       'input_ordinal': '0001', 'input': {},
                       'output': {'text': 'Prepare simulation'}, 'tool_logs': []}
                      for n in (1, 2)]}


def input_answer():
    return {**answer(), 'reference_step_ids': ['reference/1'],
            'candidate_step_ids': [], 'candidate_decisive_step': None,
            'candidate_input_ordinals': ['0001'], 'candidate_decisive_input': '0001',
            'candidate_observation': OUTPUT}


def assess(candidate, reply, tmp_path, *, ask=None):
    reference = {'agent_id': 'example', 'definition': {'defect': 'Invalid simulator state'},
                 'trajectories': [{**candidate_trace(), 'attempt': 'reference'}]}
    return detection.assess(reference, candidate, directory=tmp_path, environ={},
                            model=SimpleNamespace(model='fixture', base_url='https://example.test'),
                            ask=ask or (lambda *a, **k: reply))


@pytest.mark.parametrize('full_context', [False, True])
def test_final_input_result_is_citable_and_retained(tmp_path, full_context):
    candidate = candidate_trace()
    original = deepcopy(candidate)
    calls = []
    def ask(model, *, system, payload):
        calls.append(payload)
        assert payload['candidate_trajectory']['inputs'][0]['result']['output'] == OUTPUT
        if full_context and len(calls) == 1:
            return {'request_full_context': True, 'reason': 'Need complete request context'}
        return input_answer()
    result = assess(candidate, input_answer(), tmp_path, ask=ask)
    assert result['hit'] is True
    assert len(calls) == (2 if full_context else 1)
    assert result['evidence']['candidate'] == []
    assert result['evidence']['candidate_inputs'][0]['ordinal'] == '0001'
    assert result['evidence']['candidate_inputs'][0]['result']['output'] == OUTPUT
    assert candidate == original
    assert assess(candidate, input_answer(), tmp_path)['cache_reused']
    assert json.loads(Path(result['call_path']).read_text(encoding='utf-8'))['request']['protocol'] == 'abb.issue-trigger.v5'


def test_final_result_without_model_steps_is_usable(tmp_path):
    candidate = candidate_trace()
    candidate['steps'] = []
    assert assess(candidate, input_answer(), tmp_path)['hit'] is True


def test_negative_can_cite_observed_input_output(tmp_path):
    reply = {**input_answer(), 'match': False, 'candidate_decisive_input': None,
             'candidate_observation': None}
    assert assess(candidate_trace(), reply, tmp_path)['hit'] is False


def test_legacy_step_only_matcher_does_not_accept_input_citations():
    from agentbench.harness.ground_truth.matching import validate_match
    with pytest.raises(ValueError, match='unknown candidate Input'):
        validate_match(input_answer(), {'reference/1'}, {1, 2})


@pytest.mark.parametrize('invalid', ['wrong_input', 'unknown_step', 'both_decisive',
                                  'prompt_only', 'error_only', 'other_input', 'fabricated',
                                  'truncated', 'duplicate_input'])
def test_input_citations_cannot_borrow_unrelated_evidence(tmp_path, invalid):
    candidate, reply = candidate_trace(), input_answer()
    item = candidate['inputs'][0]
    if invalid == 'wrong_input':
        reply.update(candidate_input_ordinals=['0002'], candidate_decisive_input='0002')
    elif invalid == 'unknown_step':
        reply['candidate_step_ids'] = [999]
    elif invalid == 'both_decisive':
        reply.update(candidate_step_ids=[2], candidate_decisive_step=2)
    elif invalid in ('prompt_only', 'error_only', 'other_input'):
        item['result']['output'] = 'Unrelated result'
        if invalid == 'prompt_only':
            item['prompt'] = OUTPUT
        elif invalid == 'error_only':
            item['result']['error'] = OUTPUT
        else:
            candidate['inputs'].append({'ordinal': '0002', 'result': {'output': OUTPUT}})
    elif invalid == 'fabricated':
        reply['candidate_observation'] = 'This result never occurred.'
    elif invalid == 'truncated':
        item['result']['output'] = {'truncated': True, 'head': OUTPUT}
    else:
        candidate['inputs'].append(deepcopy(item))
    with pytest.raises(ValueError):
        assess(candidate, reply, tmp_path)


def test_step_citation_does_not_silently_search_input_results(tmp_path):
    reply = {**input_answer(), 'candidate_input_ordinals': [], 'candidate_decisive_input': None,
             'candidate_step_ids': [2], 'candidate_decisive_step': 2}
    with pytest.raises(ValueError, match='observation is absent'):
        assess(candidate_trace(), reply, tmp_path)


def test_invalid_step_can_be_corrected_to_explicit_input_citation(tmp_path):
    calls = []
    def ask(model, *, system, payload):
        calls.append(payload)
        if len(calls) == 1:
            return {**input_answer(), 'candidate_step_ids': [3], 'candidate_decisive_step': 3,
                    'candidate_input_ordinals': [], 'candidate_decisive_input': None}
        assert payload['valid_candidate_input_ordinals'] == ['0001']
        return input_answer()
    assert assess(candidate_trace(), input_answer(), tmp_path, ask=ask)['hit'] is True
    assert len(calls) == 2


@pytest.mark.parametrize('has_steps', [True, False])
def test_exp1_stops_when_final_input_result_confirms_hit(prepared, has_steps):
    f = prepared
    f.candidate.update(candidate_trace())
    if not has_steps:
        f.candidate['steps'] = []
    submitted = [case('first'), case('second')]
    path = collection(f.service.root / 'input.json', submitted)
    reply = {**input_answer(), 'reference_step_ids': answer()['reference_step_ids']}
    result = experiment(f, lambda *a, **k: reply).run('example', path, issue=1)
    assert result['score'] == 1 and result['first_hit'] == 1
    assert result['matched_case'] == submitted[0]
    assert len(f.agent.requests) == 1
    assert result['issues'][0]['unexecuted_case_ids'] == ['second']
