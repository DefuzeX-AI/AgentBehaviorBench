"""Short Case slot and attempt directory names stay stable, unique and compatible."""
import json
import re
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from agentbench.harness.registry import AgentRegistration
from agentbench.harness.scheduling.state import AgentState
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.layout import AGENT_ATTEMPTS_V1, CURRENT_LAYOUT
from agentbench.sdk.integration.artifacts import FileArtifactStore, claim_case_slot


def suite(tmp_path, suite_id='suite_0a1b2c3d'):
    root = tmp_path / 'agent'
    root.mkdir(exist_ok=True)
    agent = AgentRegistration('echo', root, True, 'ready', 'test', 'test', 3)
    with SuiteStore.begin(tmp_path / 'results/suites', suite_id, [agent]) as store:
        return store.directory


def test_new_suites_use_short_case_slots_that_resolve_stably(tmp_path):
    directory = suite(tmp_path)
    assert json.loads((directory / 'plan.json').read_text())['artifact_layout'] == CURRENT_LAYOUT
    first = FileArtifactStore(directory).case('echo', 0).directory
    assert re.fullmatch(r'[0-9a-f]{8}', first.name)
    assert first.parent == tmp_path / 'results/agents/echo/cases'
    # Every later lookup, including from a new store instance, finds the same slot.
    assert FileArtifactStore(directory).case('echo', 0).directory == first
    others = {FileArtifactStore(directory).case('echo', index).directory for index in (1, 2)}
    assert first not in others and len(others) == 2
    assert not list(first.parent.glob('.claim-*'))


def test_a_taken_slot_name_moves_to_the_next_candidate(tmp_path):
    agent = tmp_path / 'agents/echo'
    taken = agent / 'cases' / uuid5(NAMESPACE_URL, 'mine').hex[:8]
    taken.mkdir(parents=True)
    (taken / 'slot.json').write_text(json.dumps({'owner': 'someone else'}))
    (taken / 'case.json').write_text('their case')

    mine = claim_case_slot(agent, 'mine')
    assert mine != taken and re.fullmatch(r'[0-9a-f]{8}', mine.name)
    assert claim_case_slot(agent, 'mine') == mine
    assert (taken / 'case.json').read_text() == 'their case'
    assert json.loads((taken / 'slot.json').read_text())['owner'] == 'someone else'


def test_saved_v1_suites_keep_their_original_long_slots(tmp_path):
    directory = suite(tmp_path)
    plan = json.loads((directory / 'plan.json').read_text())
    plan['artifact_layout'] = AGENT_ATTEMPTS_V1
    (directory / 'plan.json').write_text(json.dumps(plan))
    case = FileArtifactStore(directory).case('echo', 1).directory
    expected = uuid5(NAMESPACE_URL, f'{directory.as_posix()}:echo:1').hex
    assert case.name == expected and len(case.name) == 32


def test_attempt_ids_are_short_and_unique_within_a_case():
    preparation = SimpleNamespace(identity={'job_id': 'job'},
                                  registration=SimpleNamespace(case_count=1))
    state = AgentState(preparation)
    case = SimpleNamespace(case_index=0, case_id='case')
    first = state.begin_attempt(case)['attempt_id']
    second = state.begin_attempt(case)['attempt_id']
    assert re.fullmatch(r'01[0-9a-f]{6}', first)
    assert re.fullmatch(r'02[0-9a-f]{6}', second)
    # Recovery keeps working in the attempt it interrupted.
    state.recoveries[0] = SimpleNamespace(attempt_id=second, attempt_number=2)
    assert state.begin_attempt(case)['attempt_id'] == second
