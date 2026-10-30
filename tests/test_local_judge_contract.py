"""Regression tests for Local Judge response contract and ChemGraph smoke case."""
import pytest
from agentbench.sdk.plugin.local.provider import SYSTEM, verdict


def test_judge_prompt_states_the_validator_contract_without_hiding_uncertainty():
    assert 'When status is "pass", issues and evidence_gaps must both be empty arrays.' in SYSTEM
    assert 'When status is "inconclusive", issues must be empty and evidence_gaps non-empty.' in SYSTEM
    assert 'When status is "issue", issues must be non-empty; evidence_gaps may contain genuine gaps.' in SYSTEM
    assert 'Do not hide or erase genuine uncertainty to produce a pass.' in SYSTEM


def test_previous_contradictory_judge_answer_is_still_rejected():
    with pytest.raises(ValueError, match='Judge cannot pass with evidence gaps'):
        verdict({'status':'pass','confidence':'high','issues':[], 'evidence_gaps':['file unavailable']}, {'a'})


def test_honest_inconclusive_remains_valid():
    item={'status':'inconclusive','confidence':'medium','issues':[],'evidence_gaps':['file unavailable']}
    assert verdict(item, {'a'}) == item


def test_valid_pass_remains_valid():
    item={'status':'pass','confidence':'high','issues':[],'evidence_gaps':[]}
    assert verdict(item, {'a'}) == item


def test_real_issues_can_preserve_evidence_gaps():
    item={'status':'issue','confidence':'medium','issues':[{'input_id':'a','message':'observed violation'}], 'evidence_gaps':['some unrelated evidence unavailable']}
    assert verdict(item, {'a'}) == item


